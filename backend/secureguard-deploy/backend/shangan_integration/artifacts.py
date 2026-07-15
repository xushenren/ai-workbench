"""
artifacts.py — Artifacts 能力的后端落地

设计要点：
1. Kun 不改代码、走标准 OpenAI 契约 → 不能往响应里塞 Kun 不认识的结构破坏兼容。
   方案：正文 content 保持完整（Kun 端就看到围栏文本，不影响）；同时把抽取出的
   结构化 artifacts 放到响应的【自定义扩展字段】x_shangan_artifacts，
   上安 /app 的 ArtifactPanel.jsx 读取它做富渲染，Kun 端忽略该字段。
2. 抽取依据 expert_router 注入的 ARTIFACT_PROTOCOL：模型用 ```artifact:{type} title="..."``` 围栏。
   兜底：未按协议输出时，对「超过 N 行的纯代码块」自动升格为 code artifact。
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, asdict
from typing import Any

ARTIFACT_FENCE = re.compile(
    r"```artifact:(?P<type>code|markdown|table|mermaid|calc)"
    r"(?:\s+title=\"(?P<title>[^\"]*)\")?"
    r"(?:\s+lang=\"(?P<lang>[^\"]*)\")?"
    r"\n(?P<body>.*?)```",
    re.DOTALL,
)
PLAIN_CODE_FENCE = re.compile(r"```(?P<lang>[a-zA-Z0-9_+-]*)\n(?P<body>.*?)```", re.DOTALL)


@dataclass
class Artifact:
    id: str
    type: str            # code | markdown | table | mermaid | calc
    title: str
    lang: str
    content: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_artifacts(content: str, *, auto_code_min_lines: int = 20) -> tuple[str, list[Artifact]]:
    """
    返回 (清洗后的正文, artifacts列表)。
    - 显式协议围栏 → 抽成 artifact，正文里替换为一行占位引用，便于 /app 锚定。
    - 未用协议但代码块 >= auto_code_min_lines → 自动升格。
    """
    artifacts: list[Artifact] = []

    def _take_explicit(m: re.Match) -> str:
        aid = uuid.uuid4().hex[:8]
        a = Artifact(
            id=aid,
            type=m.group("type"),
            title=(m.group("title") or _infer_title(m.group("body"))).strip(),
            lang=(m.group("lang") or _infer_lang(m.group("type"), m.group("body"))),
            content=m.group("body").strip("\n"),
        )
        artifacts.append(a)
        return f"⟦artifact:{aid}⟧"   # /app 用它把卡片插回正文位置；Kun 端原样显示这串短标记

    cleaned = ARTIFACT_FENCE.sub(_take_explicit, content)

    # 兜底：长代码块自动升格
    def _take_plain(m: re.Match) -> str:
        body = m.group("body")
        if body.count("\n") + 1 < auto_code_min_lines:
            return m.group(0)  # 短代码留在正文
        aid = uuid.uuid4().hex[:8]
        artifacts.append(Artifact(
            id=aid, type="code", title=_infer_title(body),
            lang=m.group("lang") or "text", content=body.strip("\n"),
        ))
        return f"⟦artifact:{aid}⟧"

    cleaned = PLAIN_CODE_FENCE.sub(_take_plain, cleaned)
    return cleaned.strip(), artifacts


def _infer_title(body: str) -> str:
    for line in body.splitlines():
        s = line.strip("#/ -\t")
        if s:
            return s[:48]
    return "未命名"


def _infer_lang(atype: str, body: str) -> str:
    if atype != "code":
        return atype
    head = body.lstrip()[:40]
    if head.startswith(("import ", "from ", "def ", "class ")):
        return "python"
    if "function" in head or "const " in head or "=>" in head:
        return "javascript"
    return "text"


def attach_to_response(openai_response: dict, artifacts: list[Artifact], cleaned_text: str) -> dict:
    """把抽取结果写回 OpenAI 兼容响应。不破坏标准结构，只加扩展字段。"""
    if not openai_response.get("choices"):
        return openai_response
    msg = openai_response["choices"][0].get("message", {})
    msg["content"] = cleaned_text                      # 正文用占位标记版（Kun 显示短标记，无害）
    openai_response["choices"][0]["message"] = msg
    openai_response["x_shangan_artifacts"] = [a.to_dict() for a in artifacts]  # /app 专用
    return openai_response
