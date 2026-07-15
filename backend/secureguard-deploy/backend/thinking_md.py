"""backend.thinking_md — MD 驱动的思考方式（主 MD + 领域次 MD，热加载）。

原理：把"怎么思考"从模型权重抽出来，写进可编辑的 MD。模型是解释器，MD 是程序。
  - 每个 MD 的 frontmatter 声明 `steps`（右侧思考面板可见的分步）。
  - 正文是注入模型的提示词脚手架。
  - 领域次 MD 用 `extends` + `steps_insert_before` 叠加在主 MD 上。
换 MD → 步骤与脚手架都变 → 思考方式变，且**无需改代码/重新部署**（每次请求重读文件）。

纯 stdlib + PyYAML，可离线测。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    import yaml  # PyYAML 可用
except Exception:  # pragma: no cover
    yaml = None

THINKING_DIR = os.environ.get(
    "THINKING_MD_DIR",
    os.path.join(os.path.dirname(__file__), "..", "config", "thinking"),
)

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


@dataclass
class Step:
    key: str
    label: str
    hint: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {"key": self.key, "label": self.label, "hint": self.hint}


@dataclass
class ThinkingProfile:
    """组合后的思考画像：可见步骤 + 注入提示词。"""
    id: str
    steps: List[Step]
    prompt_body: str
    sources: List[str] = field(default_factory=list)  # 参与组合的 MD id，便于排查

    def steps_dict(self) -> List[Dict[str, str]]:
        return [s.to_dict() for s in self.steps]

    def compose_prompt(self, question: str, context: str = "") -> str:
        ctx = f"\n\n=== 可信文档 ===\n{context}\n" if context else ""
        return f"{self.prompt_body}{ctx}\n\n=== 用户问题 ===\n{question}\n"


def _parse_md(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    m = _FRONTMATTER.match(raw)
    if not m:
        return {"meta": {}, "body": raw.strip()}
    meta_text, body = m.group(1), m.group(2)
    meta = (yaml.safe_load(meta_text) if yaml else {}) or {}
    return {"meta": meta, "body": body.strip()}


def _steps_from(meta: Dict[str, Any]) -> List[Step]:
    out: List[Step] = []
    for s in meta.get("steps", []) or []:
        if isinstance(s, dict) and s.get("key"):
            out.append(Step(s["key"], s.get("label", s["key"]), s.get("hint", "")))
    return out


def load_profile(domain: Optional[str] = None, base_dir: str = THINKING_DIR) -> ThinkingProfile:
    """加载主 MD，若给定 domain 则叠加 domain-<domain>.md。每次都重读文件 → 热加载。"""
    base_dir = os.path.abspath(base_dir)
    main = _parse_md(os.path.join(base_dir, "main.md"))
    steps = _steps_from(main["meta"])
    body = main["body"]
    sources = [main["meta"].get("id", "main")]

    if domain:
        dpath = os.path.join(base_dir, f"domain-{domain}.md")
        if os.path.exists(dpath):
            dom = _parse_md(dpath)
            sources.append(dom["meta"].get("id", f"domain-{domain}"))
            # 叠加正文
            body = f"{body}\n\n{dom['body']}"
            # 叠加步骤：插到指定 key 之前（默认 answer 前）
            insert_before = dom["meta"].get("steps_insert_before", "answer")
            extra = _steps_from(dom["meta"])
            if extra:
                idx = next((i for i, s in enumerate(steps) if s.key == insert_before), len(steps))
                steps = steps[:idx] + extra + steps[idx:]

    return ThinkingProfile(id="+".join(sources), steps=steps, prompt_body=body, sources=sources)


# ---------- 把模型的结构化输出按 step 切片，供思考面板逐步展示 ----------
def split_sections(text: str, steps: List[Step]) -> Dict[str, str]:
    """从模型输出里抽取每个 step 对应的标签段落。

    约定：step.key 'assess'→<ASSESS>，'gather'→<GATHER>… 标签为 key 大写。
    抽不到的段落返回空串（上层据此降级该步显示）。
    """
    result: Dict[str, str] = {}
    for s in steps:
        tag = s.key.upper()
        m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL | re.IGNORECASE)
        result[s.key] = m.group(1).strip() if m else ""
    return result
