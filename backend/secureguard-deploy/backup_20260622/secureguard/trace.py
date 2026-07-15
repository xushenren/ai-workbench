"""secureguard.trace — D3 思考过程双轨（public_trace / audit_trace）。

规格 §5 要把推理链实时展示给用户，但有两个硬约束：
  (a) 工具返回值/参数可能含 PII，直出=绕过输出守卫 → 渲染前必须过 L3 脱敏。
  (b) 回显具体 rule_id 等于给攻击者反馈 → 用户只看"通过/被拦截"，rule_id 仅审计可见。

因此每个原始帧 (TraceFrame) 拆成两份：
  - public_trace：用户可见。过 L3 脱敏、抹掉 rule_id、保证"永不空白"（优雅降级）。
  - audit_trace：仅 admin + 审计。完整 params/result 哈希、rule_id、tier、可接哈希链。

字段拆分见 build_* 的实现与 CONTRACT.md。纯标准库 + 复用 L3 OutputGuard。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .l3_output_guard import OutputGuard
from .l4_audit import _sha256

_OG = OutputGuard()


@dataclass
class TraceFrame:
    """一条原始推理帧（管道内部产生，未脱敏）。"""

    stage: str                       # C1/C2/C4/harness/tool/audit
    type: str                        # context_load/gap/route/gate/tool_call/audit
    summary: str = ""                # 人类可读概述
    tool_name: str = ""              # type==tool_call 时
    params: Optional[Dict[str, Any]] = None
    result: str = ""                 # 工具/模型返回（可能含敏感）
    result_count: Optional[int] = None  # 返回条目数（如检索 3 条）
    gate_result: str = ""            # PASS/BLOCK/ASK/ESCALATE（type==gate 时）
    rule_id: str = ""                # 命中的具体规则（仅审计可见）
    tier: str = ""                   # 算力 tier 名
    latency_ms: int = 0


def _sanitize_text(text: str) -> Dict[str, Any]:
    """过 L3，返回 {text, redacted, fully_redacted}。"""
    if not text:
        return {"text": "", "redacted": False, "fully_redacted": False}
    res = _OG.check(text)
    sanitized = res["sanitized_output"]
    redacted = res["quality"]["sanitization_applied"]
    # "全脱敏"判定：脱敏后正文几乎只剩占位符
    visible = sanitized.replace("[", "").replace("]", "").strip()
    fully = redacted and (len(visible) == 0 or "_REDACTED" in sanitized and len(sanitized) < 30)
    return {"text": sanitized, "redacted": redacted, "fully_redacted": fully}


def build_public_trace(frame: TraceFrame) -> Dict[str, Any]:
    """用户可见帧：脱敏、抹 rule_id、保证 display 永不空白。"""
    out: Dict[str, Any] = {
        "stage": frame.stage,
        "type": frame.type,
        "tier": frame.tier or None,
        "latency_ms": frame.latency_ms,
    }

    if frame.type == "gate":
        # 只给粗粒度结论，不回显 rule_id / tier 细节
        coarse = {"PASS": "✓ 安全检查通过", "BLOCK": "⛔ 已被安全策略拦截",
                  "ASK": "需要补充信息", "ESCALATE": "需人工批准"}.get(frame.gate_result, "已检查")
        out["display"] = coarse
        out["status"] = frame.gate_result
        return out

    if frame.type == "tool_call":
        ps = _sanitize_text(str(frame.params or {}))
        rs = _sanitize_text(frame.result)
        out["tool_name"] = frame.tool_name
        out["params_redacted"] = ps["redacted"]
        out["params"] = ps["text"]
        # 优雅降级：返回值全脱敏时，不显示空白，而是说明"调用成功+计数+隐藏原因"
        if rs["fully_redacted"]:
            cnt = f"，返回 {frame.result_count} 条结果" if frame.result_count else ""
            out["display"] = (f"✓ 工具 {frame.tool_name} 调用完成{cnt}"
                              f"（内容含隐私信息，已按隐私策略隐藏）")
            out["result"] = ""
            out["result_hidden"] = True
        else:
            out["display"] = f"✓ 工具 {frame.tool_name} 调用完成"
            out["result"] = rs["text"]
            out["result_hidden"] = False
        return out

    # context_load / gap / route / audit：summary 本身一般不含敏感，仍过一遍脱敏
    ss = _sanitize_text(frame.summary)
    out["display"] = ss["text"] if ss["text"] else "（处理中）"
    return out


def build_audit_trace(frame: TraceFrame, session_id: str = "") -> Dict[str, Any]:
    """审计 + admin 可见帧：完整信息。params/result 存哈希（不存原文）。"""
    return {
        "stage": frame.stage,
        "type": frame.type,
        "summary": frame.summary,
        "tool_name": frame.tool_name,
        "params_hash": _sha256(str(frame.params or {})),
        "result_hash": _sha256(frame.result),
        "result_count": frame.result_count,
        "gate_result": frame.gate_result,
        "rule_id": frame.rule_id,       # 仅此处保留
        "tier": frame.tier,
        "latency_ms": frame.latency_ms,
        "session_id": session_id,
    }


def split_frame(frame: TraceFrame, session_id: str = "") -> Dict[str, Any]:
    """一次拆出双轨，便于管道直接消费。"""
    return {
        "public": build_public_trace(frame),
        "audit": build_audit_trace(frame, session_id),
    }
