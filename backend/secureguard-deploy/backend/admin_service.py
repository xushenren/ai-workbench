"""backend.admin_service — 算力状态 + 管理统计聚合（B6，框架无关）。

把各服务的数据聚合成前端 AdminStats 形状。算力 Tier 在线状态开发期为静态/探测桩，
真实探测(ping vLLM / 云端 / LiteLLM)在 B7。纯聚合，可离线测。
"""
from __future__ import annotations

from typing import Any, Dict, List

# 开发期 Tier 配置（B7 换成真实探测结果）
_TIERS: List[Dict[str, Any]] = [
    {"tier": "tier1", "label": "本地 GPU", "online": True,
     "endpoint": "http://gpu-01:8001", "model": "vertical-70b"},
    {"tier": "tier2", "label": "自有云端", "online": True,
     "endpoint": "http://cloud:8001", "model": "qwen-72b"},
    {"tier": "tier3", "label": "外部 API", "online": False,
     "endpoint": "litellm://gateway", "model": "deepseek / claude"},
]


def compute_status() -> List[Dict[str, Any]]:
    """算力三级在线状态。开发期静态；B7 换真实探测。"""
    return [dict(t) for t in _TIERS]


def admin_stats(state: Any) -> Dict[str, Any]:
    """聚合 6 统计卡 + 4 面板数据，对齐前端 AdminStats。"""
    agents = list(state.agent_service._agents.values())
    kbs = list(getattr(state, "kb_service", None)._kbs.values()) if getattr(state, "kb_service", None) else []
    auditor = state.auditor

    # 红线触发次数：审计里 BLOCK 决策 + 记录的 redline_hits
    redline_hits = sum(1 for e in auditor.entries if e.decision == "BLOCK")
    redline_hits += len(getattr(auditor, "redline_hits", []))

    # 本月 token：配额已用之和（内存近似）
    monthly_tokens = 0
    q = getattr(state, "quota", None)
    if q is not None:
        monthly_tokens = sum(rec.get("used", 0) for rec in q._rec.values())

    # 用户数：auth 内存表
    users = len(getattr(state.auth, "_users", {}))

    quotas_panel = []
    for a in agents:
        if q is not None:
            # 汇总该智能体所有用户的占用（演示用取首条；真实按维度统计）
            recs = [r for (uid, aid), r in q._rec.items() if aid == a["id"]]
            used = sum(r["used"] for r in recs)
        else:
            used = 0
        quotas_panel.append({
            "agent": a["name"], "used": used,
            "limit": int(a.get("free_quota_tokens", 10000)),
            "freeze": "超额冻结至下月 1 日",
        })

    recent_audit = [
        {"hash": e.entry_hash[:7], "time": e.timestamp[11:19], "decision": e.decision}
        for e in auditor.entries[-5:]
    ]

    return {
        "users": users,
        "agents": len(agents),
        "compute_nodes": len(_TIERS),
        "monthly_tokens": monthly_tokens,
        "knowledge_bases": len(kbs),
        "redline_hits": redline_hits,
        "tiers": compute_status(),
        "quotas": quotas_panel,
        "guards": {"redlines": 19, "self_monitor": 18, "domain_guards": 6, "audit_retention_days": 30},
        "recent_audit": recent_audit,
    }
