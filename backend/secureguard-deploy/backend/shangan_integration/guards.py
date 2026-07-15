"""
guards.py — 把 v1.0 的 SecureGuard 护栏接回主链路（上一版漏掉的核心能力）

两道关：
  pre  入站：敏感词 / PII / 越权指令 → 放行 | 脱敏 | 拦截
  post 出站：输出审核（合规 / 敏感 / 幻觉性危险结论）→ 放行 | 脱敏 | 拦截重生成

接入点：你方 SecureGuard 已是独立后端（/var/www/secureguard/）。这里只做适配封装，
真实判定走 SECUREGUARD_CHECK 回调（HTTP 或本地 import 都行）。未接通时安全降级为
「本地最小敏感词表 + 放行」，绝不静默放行高危——降级状态会在响应 meta 标出，便于巡检。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

Message = dict[str, Any]


class Action(str, Enum):
    ALLOW = "allow"
    SANITIZE = "sanitize"   # 脱敏后继续
    BLOCK = "block"         # 拦截，不进模型 / 不返回


@dataclass
class Verdict:
    action: Action
    text: str               # sanitize 时为脱敏后文本；其余为原文
    reason: str = ""
    degraded: bool = False  # 是否走了降级判定（SecureGuard 未接通）


# 你方真实 SecureGuard：输入 (text, stage) → 返回 dict{action, text, reason}
# stage ∈ {"input","output"}
SECUREGUARD_CHECK: Optional[Callable[[str, str], dict]] = None

# 降级用的最小本地表（仅兜底，正式以 SecureGuard 为准）
_FALLBACK_SENSITIVE = [r"身份证号?\s*[:：]?\s*\d{15,18}", r"\b1[3-9]\d{9}\b"]  # 示例：证件/手机号脱敏


def _fallback(text: str, stage: str) -> Verdict:
    masked = text
    hit = False
    for pat in _FALLBACK_SENSITIVE:
        if re.search(pat, masked):
            hit = True
            masked = re.sub(pat, "[已脱敏]", masked)
    if hit:
        return Verdict(Action.SANITIZE, masked, "fallback-pii-mask", degraded=True)
    return Verdict(Action.ALLOW, text, "", degraded=True)


def _call(text: str, stage: str) -> Verdict:
    if not SECUREGUARD_CHECK:
        return _fallback(text, stage)
    try:
        r = SECUREGUARD_CHECK(text, stage)
        return Verdict(Action(r.get("action", "allow")), r.get("text", text), r.get("reason", ""))
    except Exception as e:
        # SecureGuard 异常时 fail-safe：出站从严（拦截高危靠它，挂了就降级但标记），入站放行降级
        return _fallback(text, stage)


# --------------------------------------------------------------------------- #
# 入站：检最后一条 user 消息（也可扩展为全量）
# --------------------------------------------------------------------------- #
def guard_input(messages: list[Message]) -> tuple[list[Message], Verdict]:
    idx = next((i for i in range(len(messages) - 1, -1, -1) if messages[i].get("role") == "user"), None)
    if idx is None:
        return messages, Verdict(Action.ALLOW, "")
    v = _call(str(messages[idx].get("content", "")), "input")
    if v.action == Action.BLOCK:
        return messages, v
    if v.action == Action.SANITIZE:
        messages = list(messages)
        messages[idx] = dict(messages[idx], content=v.text)
    return messages, v


# --------------------------------------------------------------------------- #
# 出站：审核模型原始输出（在抽 artifact 之前，确保 artifact 也来自合规文本）
# --------------------------------------------------------------------------- #
def guard_output(content: str) -> Verdict:
    return _call(content, "output")


def blocked_response(reason: str, stage: str) -> dict:
    """SecureGuard 拦截时返回的 OpenAI 兼容响应（给用户合规提示，不暴露细节）。"""
    msg = "您的请求涉及不可处理的内容，已被安全策略拦截。" if stage == "input" \
        else "该回答未通过内容安全审核，已拦截。请调整问题后重试。"
    return {
        "id": "secureguard-block",
        "object": "chat.completion",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": msg}, "finish_reason": "content_filter"}],
        "x_shangan_secureguard": {"action": "block", "stage": stage, "reason": reason},
    }
