"""
grounding.py — 把 v1.0 知识引擎的真正价值接回主链路

补三件上一版没落地的事：
  1. RAG grounding：拿 22074 切片做检索增强，答案有据可依（而不是只靠模型记忆）
  2. 自动引用：检索到的每条切片编号 [S1][S2]…，注入上下文 + 要求模型按编号引用，
     出站再把用到的来源附成「参考来源」清单（spec 任务1 的"答案带来源标注"）
  3. 施工"宪法"规则：constitution_rules 作为**硬约束**注入 system，命中专业的强制条款优先

检索走注入的 RAG_SEARCH 回调（与 mcp_server 共用同一个底层检索），未接通时整体降级为
「不注入、不强制引用」，主链路照常——即不接知识库也能答，只是退回 v0 的纯模型回答。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

Message = dict[str, Any]

# (query, filters) -> [{content, source_type, source_id, skill_id, standards_ref, score}]
RAG_SEARCH: Optional[Callable[[str, dict], list[dict]]] = None


@dataclass
class Source:
    tag: str          # S1, S2, ...
    content: str
    source_type: str  # slice | standard | constitution | causal
    source_id: str
    ref: str = ""     # 标准号 / 文件名


def retrieve(query: str, skill_ids: list[str], top_k: int = 6, rules_k: int = 4) -> list[Source]:
    """检索常规知识切片 + 命中专业的宪法/标准硬条款。"""
    if not RAG_SEARCH:
        return []
    sources: list[Source] = []
    n = 0

    def _add(hits: list[dict]):
        nonlocal n
        for h in hits:
            n += 1
            sources.append(Source(
                tag=f"S{n}",
                content=str(h.get("content", "")).strip(),
                source_type=h.get("source_type", "slice"),
                source_id=str(h.get("source_id", h.get("doc_id", n))),
                ref=h.get("standards_ref", "") or h.get("source", ""),
            ))

    # 1) 常规切片（可按 skill 过滤）
    f = {"skill_id": skill_ids[0]} if skill_ids else {}
    _add(RAG_SEARCH(query, {**f, "top_k": top_k}))
    # 2) 宪法/标准硬条款（强制优先级，单独检索保证不被普通切片挤掉）
    _add(RAG_SEARCH(query, {"source_type": "constitution", "top_k": rules_k}))
    return sources


def inject(messages: list[Message], sources: list[Source]) -> list[Message]:
    """把来源编号注入 system，并要求模型按 [S#] 引用；宪法条款标为强制。"""
    if not sources:
        return messages
    lines = []
    rules = [s for s in sources if s.source_type in ("constitution", "standard")]
    refs = [s for s in sources if s not in rules]
    if rules:
        lines.append("【强制规范（违反即错，优先级最高）】")
        lines += [f"[{s.tag}] {s.content}" + (f"（{s.ref}）" if s.ref else "") for s in rules]
    if refs:
        lines.append("\n【参考资料（据此作答，按编号引用）】")
        lines += [f"[{s.tag}] {s.content}" for s in refs]
    grounding_msg = {
        "role": "system",
        "content": (
            "回答必须基于下列资料，关键结论后用 [S#] 标注来源；资料未覆盖处明确说明"
            "「依据通用工程经验」，不要编造规范号或数据。\n\n" + "\n".join(lines)
        ),
    }
    # 放在 Skill 注入之后、对话之前
    sys = [m for m in messages if m.get("role") == "system"]
    body = [m for m in messages if m.get("role") != "system"]
    return sys + [grounding_msg] + body


CITE = re.compile(r"\[S(\d+)\]")


def append_sources(content: str, sources: list[Source]) -> str:
    """出站：把正文实际引用到的来源整理成「参考来源」清单（自动引用落地）。"""
    used = {f"S{m}" for m in CITE.findall(content)}
    if not used:
        return content
    by_tag = {s.tag: s for s in sources}
    listed = [by_tag[t] for t in sorted(used, key=lambda x: int(x[1:])) if t in by_tag]
    if not listed:
        return content
    block = "\n\n---\n参考来源：\n" + "\n".join(
        f"[{s.tag}] {s.ref or s.source_id}"
        f"（{ {'constitution':'施工宪法','standard':'标准条文','slice':'知识库','causal':'因果链'}.get(s.source_type, s.source_type) }）"
        for s in listed
    )
    return content + block
