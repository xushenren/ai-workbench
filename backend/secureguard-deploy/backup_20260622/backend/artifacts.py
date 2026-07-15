"""backend.artifacts — 从模型输出提取代码块，生成 Artifact（问题3）。

Artifact = 可在前端"工作区侧栏"展示的文件卡片（文件名、语言、内容）。
多文件可由前端 JSZip 打包下载；README 由 artifact 列表拼成。
纯 stdlib，可离线测。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

# 语言 → (文件扩展, 图标)。前端据此显示。
_LANG: Dict[str, Dict[str, str]] = {
    "python": {"ext": "py", "icon": "🐍"},
    "typescript": {"ext": "ts", "icon": "🔷"},
    "javascript": {"ext": "js", "icon": "🟨"},
    "tsx": {"ext": "tsx", "icon": "🔷"},
    "html": {"ext": "html", "icon": "🌐"},
    "css": {"ext": "css", "icon": "🎨"},
    "json": {"ext": "json", "icon": "📋"},
    "markdown": {"ext": "md", "icon": "📝"},
    "bash": {"ext": "sh", "icon": "💻"},
    "sql": {"ext": "sql", "icon": "🗃️"},
}

_FENCE = re.compile(r"```([a-zA-Z0-9+#]*)\n(.*?)```", re.DOTALL)


@dataclass
class Artifact:
    filename: str
    language: str
    content: str
    icon: str = "📄"
    runnable: bool = False  # python/html 可在工作区运行/预览

    def to_event(self) -> Dict[str, Any]:
        return {"event": "artifact", "filename": self.filename, "language": self.language,
                "content": self.content, "icon": self.icon, "runnable": self.runnable}


def extract_artifacts(text: str) -> List[Artifact]:
    """从一段文本里抽取所有 ```lang fenced 代码块，生成 Artifact。"""
    out: List[Artifact] = []
    seen = 0
    for m in _FENCE.finditer(text):
        lang = (m.group(1) or "text").lower()
        code = m.group(2).rstrip("\n")
        if not code.strip():
            continue
        meta = _LANG.get(lang, {"ext": "txt", "icon": "📄"})
        seen += 1
        out.append(Artifact(
            filename=f"snippet_{seen}.{meta['ext']}",
            language=lang,
            content=code,
            icon=meta["icon"],
            runnable=lang in ("python", "html", "javascript"),
        ))
    return out


def first_python(text: str) -> str:
    """取第一段 Python 代码（供 VERIFY 步喂沙箱执行）。无则空串。"""
    for a in extract_artifacts(text):
        if a.language == "python":
            return a.content
    return ""


def build_readme(artifacts: List[Artifact]) -> Artifact:
    """把 artifact 列表拼成 README.md（作为最后一个 artifact，便于打包）。"""
    lines = ["# 交付文件清单\n"]
    for a in artifacts:
        lines.append(f"- {a.icon} `{a.filename}` ({a.language})")
    return Artifact(filename="README.md", language="markdown", content="\n".join(lines), icon="📝")


def format_verify(result: Dict[str, Any]) -> str:
    """把沙箱执行结果格式化成 VERIFY 步的 display 文本。"""
    if not result.get("available"):
        return "未执行验证（沙箱未部署）。应跑的测试：输入边界 / 异常路径 / 预期输出。"
    if result.get("timed_out"):
        return f"❌ 执行超时（>{result.get('error', '').replace('timeout_', '')}）"
    if result.get("error"):
        return f"⚠️ 执行异常：{result['error']}"
    ok = result.get("exit_code") == 0
    dur = result.get("duration_ms", 0) / 1000
    head = f"{'✅ 通过' if ok else '❌ 失败'} ({dur:.1f}s)"
    body = result.get("stdout") if ok else (result.get("stderr") or result.get("stdout"))
    body = (body or "").strip()
    return f"{head}\n--- {'stdout' if ok else 'stderr'} ---\n{body}" if body else head
