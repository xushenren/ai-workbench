"""secureguard.compute_router — 算力三级路由 + 数据分级门。

回应企业工作台规格里最大的隐患：Tier 3 是**外部 API**（OpenAI/DeepSeek/Claude…），
而产品是**部署在企业自有服务器**。若敏感/PII 数据随"自动降级"流到 Tier 3，
就等于数据出境，直接违反红线 R-10（数据外泄出已批准边界）。

因此路由不能只看"可用性 + 成本"，必须先过**数据分级门**：

    内容 → 分级(PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED)
         → 按分级决定"允许哪些 Tier"
         → 再在允许集合内按 可用性/成本/强制策略 选 Tier

关键策略：
  - RESTRICTED（含凭据/PII）/ CONFIDENTIAL：**禁止** Tier 3 外部 API。
    若内网 Tier 1/2 都不可用 → fail-closed 拒绝（不偷偷降级出境）。
  - 敏感任务（红线 R0/R1 强制内网）：锁 Tier 1，不降级（对齐规格"紧急强制 Tier 1"）。
  - Tier 3 配额超限 → 熔断该 Tier。
  - 其余（PUBLIC/INTERNAL 且无强制）：Tier 1→2→3 按可用性降级。

复用 SecureGuard 既有敏感模式（L0/L3）做分级，纯标准库，可离线测试。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional

from .l0_input_guard import InputGuard
from .l3_output_guard import OutputGuard


class Tier(IntEnum):
    LOCAL = 1          # Tier 1 本地 GPU（内网）
    PRIVATE_CLOUD = 2  # Tier 2 自有云端（仍属可信边界）
    EXTERNAL_API = 3   # Tier 3 外部 API（边界外！）


class DataClass(IntEnum):
    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3     # 含凭据 / PII，最高敏感


# 各数据分级"允许使用的最高 Tier"。RESTRICTED/CONFIDENTIAL 禁止外部 API。
_ALLOWED_MAX_TIER = {
    DataClass.PUBLIC: Tier.EXTERNAL_API,
    DataClass.INTERNAL: Tier.EXTERNAL_API,   # 内部信息可用外部 API（按企业策略，可收紧）
    DataClass.CONFIDENTIAL: Tier.PRIVATE_CLOUD,  # 仅限可信边界内
    DataClass.RESTRICTED: Tier.LOCAL,            # 只允许本地
}

# 内部信息标记（可按企业自定义扩展，建议外置到 Plane-1 配置）
_INTERNAL_MARKERS = re.compile(
    r"(内部|机密|保密|confidential|internal[\s_-]*only|不对外|仅限内部|商业秘密)",
    re.IGNORECASE,
)

# 本地化 PII 模式（企业场景的 PII 是身份证/手机号，而非美式 SSN）
_PII_PATTERNS = [
    re.compile(r"\b\d{17}[\dXx]\b"),          # 中国居民身份证 18 位
    re.compile(r"\b1[3-9]\d{9}\b"),           # 中国手机号 11 位
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),     # US SSN
    re.compile(r"\b62\d{14,17}\b"),           # 银联卡号（62 开头，相对精确）
]


@dataclass
class TierStatus:
    """某 Tier 当前可用性与配额状态。"""

    available: bool = True
    quota_exhausted: bool = False  # 仅 Tier 3 相关


@dataclass
class RouteDecision:
    allowed: bool
    tier: Optional[Tier]
    data_class: DataClass
    reason: str
    downgraded: bool = False
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "tier": int(self.tier) if self.tier else None,
            "tier_name": self.tier.name if self.tier else None,
            "data_class": self.data_class.name,
            "reason": self.reason,
            "downgraded": self.downgraded,
            "notes": self.notes,
        }


# Tier 名称（与智能体 YAML 配置里的 tier1/tier2/tier3 对齐）
_TIER_BY_NAME = {"tier1": Tier.LOCAL, "tier2": Tier.PRIVATE_CLOUD, "tier3": Tier.EXTERNAL_API}


@dataclass
class AgentComputePolicy:
    """D2 终稿：每个智能体的算力策略，由管理员按业务场景配置。

    示例（HR助手仅内网 / 通用问答可用外部 API）：
        AgentComputePolicy(allowed_tiers=["tier1"], force_local_for=["R0","R1"])
        AgentComputePolicy(allowed_tiers=["tier1","tier2","tier3"])
    """

    allowed_tiers: List[str] = field(default_factory=lambda: ["tier1"])
    preferred_order: List[str] = field(default_factory=list)  # 空则按 allowed_tiers 顺序
    force_local_for: List[str] = field(default_factory=lambda: ["R0", "R1"])
    fail_strategy: str = "closed"  # closed=全挂则拒绝 / open=允许降级到 external

    def allowed_set(self):
        return {_TIER_BY_NAME[t] for t in self.allowed_tiers if t in _TIER_BY_NAME}


class DataClassifier:
    """内容数据分级。复用 SecureGuard 的敏感模式检测 PII/凭据。"""

    def __init__(self) -> None:
        self._input_guard = InputGuard()
        self._sens = [re.compile(p, re.IGNORECASE) for p, _ in OutputGuard.SENSITIVE_PATTERNS]

    def classify(self, content: str, declared: Optional[DataClass] = None) -> DataClass:
        """返回内容分级。declared 为调用方声明的下限，取检测与声明的较高者。"""
        level = DataClass.PUBLIC

        # 凭据/PII 命中（复用 L3 敏感模式）→ RESTRICTED
        if any(p.search(content) for p in self._sens) or any(p.search(content) for p in _PII_PATTERNS):
            level = DataClass.RESTRICTED
        else:
            # 凭据索要类陷阱也视为高敏感
            traps = {t.trap_type for t in self._input_guard.scan(content)}
            if "credential_leak" in traps or "data_exfil" in traps:
                level = DataClass.RESTRICTED
            elif _INTERNAL_MARKERS.search(content):
                level = DataClass.CONFIDENTIAL

        if declared is not None and declared > level:
            level = declared
        return level


class ComputeRouter:
    """算力路由器：数据分级门 → 可用性/强制策略选 Tier。"""

    def __init__(self, classifier: Optional[DataClassifier] = None) -> None:
        self.classifier = classifier or DataClassifier()

    def classify_for_audit(self, content: str) -> Dict[str, Any]:
        """D2 终稿：分级门不再决定路由，只在检出 PII/凭据时产出审计告警。"""
        dc = self.classifier.classify(content)
        return {
            "data_class": dc.name,
            "pii_alert": dc >= DataClass.CONFIDENTIAL,  # 机密及以上触发告警
            "severity": "high" if dc == DataClass.RESTRICTED else
                        ("medium" if dc == DataClass.CONFIDENTIAL else "none"),
        }

    def route_by_policy(
        self,
        content: str,
        policy: "AgentComputePolicy",
        tier_status: Dict[Tier, TierStatus],
        *,
        risk_level: Optional[str] = None,   # "R0"/"R1"/"R2"，用于 force_local_for
    ) -> RouteDecision:
        """D2 终稿主路径：按【智能体的 compute_policy】决定算力，分级仅作审计告警。

        管理员通过 policy.allowed_tiers 为每个智能体分配算力边界；这里不再用
        数据分级去否决路由（HR助手只配 tier1 这种隔离由管理员在 policy 里表达）。
        """
        audit = self.classify_for_audit(content)
        notes = [f"audit_class={audit['data_class']}",
                 f"pii_alert={audit['pii_alert']}"]
        dc = DataClass[audit["data_class"]]

        # 1) 敏感任务强制本地（policy.force_local_for 命中风险级）
        if risk_level and risk_level in policy.force_local_for:
            st = tier_status.get(Tier.LOCAL, TierStatus())
            if st.available:
                return RouteDecision(True, Tier.LOCAL, dc,
                                     f"force_local_for={risk_level}", notes=notes)
            if policy.fail_strategy == "closed":
                return RouteDecision(False, None, dc,
                                     "force_local 且 Tier1 不可用 → fail-closed", notes=notes)

        # 2) 按 policy.preferred_order 在 allowed_tiers 内选第一个可用者
        order = policy.preferred_order or policy.allowed_tiers
        downgraded = False
        first = True
        for tname in order:
            tier = _TIER_BY_NAME.get(tname)
            if tier is None or tier not in policy.allowed_set():
                continue
            st = tier_status.get(tier, TierStatus())
            if not st.available or (tier == Tier.EXTERNAL_API and st.quota_exhausted):
                downgraded = True
                first = False
                continue
            reason = f"policy_selected={tier.name}" + ("（已降级）" if not first else "")
            return RouteDecision(True, tier, dc, reason, downgraded=downgraded, notes=notes)

        # 3) allowed_tiers 内无可用算力 → 按 fail_strategy
        if policy.fail_strategy == "open" and Tier.EXTERNAL_API in policy.allowed_set():
            st = tier_status.get(Tier.EXTERNAL_API, TierStatus())
            if st.available and not st.quota_exhausted:
                return RouteDecision(True, Tier.EXTERNAL_API, dc, "fail_open→external",
                                     downgraded=True, notes=notes)
        return RouteDecision(False, None, dc,
                             "allowed_tiers 内无可用算力 → fail-closed 拒绝", notes=notes)

    def route(
        self,
        content: str,
        tier_status: Dict[Tier, TierStatus],
        *,
        declared_class: Optional[DataClass] = None,
        force_local: bool = False,       # 敏感任务（红线 R0/R1）强制 Tier 1
        locked_tier: Optional[Tier] = None,  # 管理员为智能体锁定 Tier
    ) -> RouteDecision:
        dc = self.classifier.classify(content, declared_class)
        notes: List[str] = [f"classified={dc.name}"]

        # 1) 强制本地（敏感任务）：只认 Tier 1，不降级
        if force_local:
            st = tier_status.get(Tier.LOCAL, TierStatus())
            if st.available:
                return RouteDecision(True, Tier.LOCAL, dc, "force_local: 敏感任务锁 Tier1", notes=notes)
            return RouteDecision(False, None, dc,
                                 "force_local 但 Tier1 不可用 → fail-closed 拒绝",
                                 notes=notes)

        # 2) 数据分级门：算出该分级允许的最高 Tier
        max_tier = _ALLOWED_MAX_TIER[dc]
        notes.append(f"max_allowed_tier={max_tier.name}")

        # 3) 管理员锁定 Tier：必须仍在分级允许范围内，否则拒绝（安全优先于锁定）
        if locked_tier is not None:
            if locked_tier > max_tier:
                return RouteDecision(False, None, dc,
                                     f"锁定 {locked_tier.name} 超出 {dc.name} 允许的 {max_tier.name}",
                                     notes=notes)
            st = tier_status.get(locked_tier, TierStatus())
            if not st.available or (locked_tier == Tier.EXTERNAL_API and st.quota_exhausted):
                return RouteDecision(False, None, dc,
                                     f"锁定的 {locked_tier.name} 不可用/超额", notes=notes)
            return RouteDecision(True, locked_tier, dc, f"locked={locked_tier.name}", notes=notes)

        # 4) 在允许范围内按 Tier1→2→3 降级选第一个可用者
        downgraded = False
        for tier in (Tier.LOCAL, Tier.PRIVATE_CLOUD, Tier.EXTERNAL_API):
            if tier > max_tier:
                # 触及分级红线：不允许的更高 Tier 一律跳过（绝不出境）
                continue
            st = tier_status.get(tier, TierStatus())
            if not st.available:
                downgraded = True
                continue
            if tier == Tier.EXTERNAL_API and st.quota_exhausted:
                downgraded = True
                continue
            reason = f"selected={tier.name}" + ("（已降级）" if downgraded else "")
            return RouteDecision(True, tier, dc, reason, downgraded=downgraded, notes=notes)

        # 5) 允许范围内无可用 Tier → fail-closed
        return RouteDecision(False, None, dc,
                             f"{dc.name} 允许范围内（≤{max_tier.name}）无可用算力 → fail-closed 拒绝",
                             notes=notes)
