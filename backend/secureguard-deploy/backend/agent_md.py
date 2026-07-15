"""backend.agent_md — 用 MD 文件定义/导入/导出智能体。

一个智能体 = 一个 MD 文件：
  - frontmatter（--- 之间）：元信息（名字/领域/图标/可见性/范围/思考法/知识库/模型）
  - 正文：智能体的系统提示词 / 人设 / 规则

与本系统的"MD 驱动"一脉相承：思考用 MD，智能体也用 MD。开放标准，可导入导出。
纯 stdlib（用已装的 PyYAML 解析 frontmatter），可离线测。

示例：
---
name: 法务助手
domain: legal
icon: ⚖️
visibility: public          # public | private | department
scope: domain_only          # open | domain_only
thinking: main              # 用哪套思考 MD（main / software ...）
knowledge_bases: [kb_law]
model: deepseek-chat         # 可选，默认内置
---
你是一名严谨的法务助手。回答必须引用条款来源，不确定就明说……
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

try:
    import yaml
    _HAS_YAML = True
except ImportError:  # pragma: no cover
    _HAS_YAML = False

# 允许的字段（白名单：防 MD 注入越权字段，如 owner_id/status 不可由 MD 指定）
_META_FIELDS = {"name", "domain", "icon", "visibility", "scope", "thinking",
                "description", "model", "tier"}
_VALID_VISIBILITY = {"public", "private", "department"}
_VALID_SCOPE = {"open", "domain_only"}


def _split_frontmatter(text: str) -> Tuple[str, str]:
    """拆出 frontmatter 与正文。无 frontmatter 时 frontmatter 为空、全部作正文。"""
    t = text.lstrip("\ufeff").lstrip()
    if t.startswith("---"):
        parts = t.split("---", 2)
        if len(parts) >= 3:
            return parts[1].strip(), parts[2].strip()
    return "", text.strip()


def parse_agent_md(text: str) -> Dict[str, Any]:
    """解析智能体 MD → 规范化 payload（供 agent_service.create）。

    校验：name 必填；visibility/scope 取合法值否则回退默认；未知 frontmatter 字段忽略。
    正文 = 系统提示词，存入 payload['system_prompt']。
    """
    if not _HAS_YAML:  # pragma: no cover
        raise RuntimeError("缺少 PyYAML，无法解析智能体 MD frontmatter")
    fm_text, body = _split_frontmatter(text)
    meta: Dict[str, Any] = {}
    if fm_text:
        try:
            loaded = yaml.safe_load(fm_text) or {}
            if isinstance(loaded, dict):
                meta = loaded
        except yaml.YAMLError as e:
            raise ValueError(f"frontmatter 解析失败：{e}")

    name = str(meta.get("name", "")).strip()
    if not name:
        raise ValueError("智能体 MD 必须在 frontmatter 指定 name")

    # 知识库引用：支持 knowledge_bases: [a, b] 或单个字符串
    kbs = meta.get("knowledge_bases", [])
    if isinstance(kbs, str):
        kbs = [kbs]
    elif not isinstance(kbs, list):
        kbs = []

    visibility = str(meta.get("visibility", "private")).lower()
    if visibility not in _VALID_VISIBILITY:
        visibility = "private"
    scope = str(meta.get("scope", "domain_only")).lower()
    if scope not in _VALID_SCOPE:
        scope = "domain_only"

    payload: Dict[str, Any] = {
        "name": name,
        "domain": str(meta.get("domain", "general")).strip() or "general",
        "icon": str(meta.get("icon", "🤖")).strip() or "🤖",
        "visibility": visibility,
        "scope": scope,
        "tier": str(meta.get("tier", "tier1")).strip() or "tier1",
        "description": str(meta.get("description", "")).strip(),
        "thinking": str(meta.get("thinking", "")).strip(),   # 空 = 按 domain 自动选
        "model": str(meta.get("model", "")).strip(),         # 空 = 内置
        "knowledge_bases": [str(k).strip() for k in kbs if str(k).strip()],
        "kb_count": len([k for k in kbs if str(k).strip()]),
        "system_prompt": body,
    }
    return payload


def to_agent_md(agent: Dict[str, Any], system_prompt: str = "") -> str:
    """把一个智能体反向导出成 MD（便于备份/迁移/分享）。"""
    lines: List[str] = ["---"]
    lines.append(f"name: {agent.get('name', '未命名智能体')}")
    for k in ("domain", "icon", "visibility", "scope", "tier"):
        if agent.get(k):
            lines.append(f"{k}: {agent[k]}")
    if agent.get("description"):
        lines.append(f"description: {agent['description']}")
    if agent.get("thinking"):
        lines.append(f"thinking: {agent['thinking']}")
    if agent.get("model"):
        lines.append(f"model: {agent['model']}")
    kbs = agent.get("knowledge_bases") or []
    if kbs:
        lines.append("knowledge_bases: [" + ", ".join(kbs) + "]")
    lines.append("---")
    lines.append("")
    lines.append(system_prompt or agent.get("system_prompt", "") or "（无系统提示词）")
    return "\n".join(lines)
