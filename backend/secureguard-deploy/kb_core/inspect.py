"""
kb_core.inspect — AI 体检(副手,不裁决)。

claim 级一致性:把待入库知识的 claims(键→值)与公有高置信池逐键比对,
同键不同值 = 冲突点。再加垃圾/注入的简单异常检查。
这是确定性的基线实现;生产可把 inspector 换成走网关的模型(更强的语义判断),
但角色不变:只产出"给专家的报告",不自动封人、不定真伪。
"""
from __future__ import annotations

from typing import Callable, Optional

from .models import Inspection, KBEntry, Pool
from .repository import KBRepo

# 可注入:走网关模型的强体检。签名 (entry, high_pool) -> Inspection
ModelInspector = Optional[Callable[[KBEntry, list[KBEntry]], Inspection]]

_SUSPICIOUS = ("http://", "https://", "ignore previous", "忽略以上", "system prompt", "<script")


def inspect(repo: KBRepo, entry: KBEntry, model_inspector: ModelInspector = None) -> Inspection:
    high = repo.by_pool(entry.tenant_id, Pool.PUBLIC_HIGH)
    if model_inspector:
        return model_inspector(entry, high)

    conflicts: list[str] = []
    # claim 级冲突:同键不同值
    high_claims: dict[str, set[str]] = {}
    for h in high:
        for k, v in h.claims.items():
            high_claims.setdefault(k, set()).add(v)
    for k, v in entry.claims.items():
        if k in high_claims and v not in high_claims[k]:
            conflicts.append(f"{k}: 拟入「{v}」, 高置信池为「{'/'.join(sorted(high_claims[k]))}」")

    anomalies: list[str] = []
    blob = (entry.title + " " + entry.content).lower()
    for s in _SUSPICIOUS:
        if s in blob:
            anomalies.append(f"可疑内容: {s}")
    if not entry.content.strip():
        anomalies.append("内容为空")

    advice = "建议复核:与高置信池冲突" if conflicts else ("注意异常项" if anomalies else "未见冲突,可入库")
    return Inspection(conflicts=conflicts, anomalies=anomalies, confidence_advice=advice)
