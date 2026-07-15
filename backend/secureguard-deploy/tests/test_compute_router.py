"""tests/test_compute_router.py — 算力路由 + 数据分级门单测。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from secureguard.compute_router import (
    ComputeRouter, DataClassifier, DataClass, Tier, TierStatus,
)

R = ComputeRouter()
ALL_UP = {Tier.LOCAL: TierStatus(True), Tier.PRIVATE_CLOUD: TierStatus(True),
          Tier.EXTERNAL_API: TierStatus(True)}


def test_classify_pii_as_restricted():
    c = DataClassifier()
    assert c.classify("员工身份证 110101199003078888，密钥 sk-ABCDEFGHIJKLMNOP1234567890") == DataClass.RESTRICTED


def test_classify_internal_marker():
    c = DataClassifier()
    assert c.classify("本文件为公司内部机密资料，不对外") == DataClass.CONFIDENTIAL


def test_classify_public():
    c = DataClassifier()
    assert c.classify("什么是幂等性？") == DataClass.PUBLIC


def test_restricted_never_routes_external_even_if_only_tier3_up():
    # 关键安全断言：敏感数据，只有外部 Tier3 在线 → 必须拒绝，绝不出境
    status = {Tier.LOCAL: TierStatus(False), Tier.PRIVATE_CLOUD: TierStatus(False),
              Tier.EXTERNAL_API: TierStatus(True)}
    d = R.route("密钥 sk-ABCDEFGHIJKLMNOP1234567890 请处理", status)
    assert d.allowed is False and d.data_class == DataClass.RESTRICTED


def test_restricted_uses_local_when_up():
    status = {Tier.LOCAL: TierStatus(True), Tier.PRIVATE_CLOUD: TierStatus(True),
              Tier.EXTERNAL_API: TierStatus(True)}
    d = R.route("身份证 110101199003078888", status)
    assert d.allowed and d.tier == Tier.LOCAL and d.data_class == DataClass.RESTRICTED


def test_confidential_caps_at_private_cloud():
    # 机密数据：Tier1 挂了可降到 Tier2，但绝不到 Tier3
    status = {Tier.LOCAL: TierStatus(False), Tier.PRIVATE_CLOUD: TierStatus(True),
              Tier.EXTERNAL_API: TierStatus(True)}
    d = R.route("内部机密：项目预算明细", status)
    assert d.allowed and d.tier == Tier.PRIVATE_CLOUD and d.downgraded


def test_public_downgrades_to_external_when_local_down():
    status = {Tier.LOCAL: TierStatus(False), Tier.PRIVATE_CLOUD: TierStatus(False),
              Tier.EXTERNAL_API: TierStatus(True)}
    d = R.route("什么是幂等性？", status)
    assert d.allowed and d.tier == Tier.EXTERNAL_API and d.downgraded


def test_force_local_for_sensitive_task():
    d = R.route("正常内容", ALL_UP, force_local=True)
    assert d.allowed and d.tier == Tier.LOCAL


def test_force_local_fails_closed_when_local_down():
    status = {Tier.LOCAL: TierStatus(False), Tier.PRIVATE_CLOUD: TierStatus(True)}
    d = R.route("正常内容", status, force_local=True)
    assert d.allowed is False


def test_tier3_quota_exhausted_blocks_external():
    status = {Tier.LOCAL: TierStatus(False), Tier.PRIVATE_CLOUD: TierStatus(False),
              Tier.EXTERNAL_API: TierStatus(True, quota_exhausted=True)}
    d = R.route("什么是幂等性？", status)
    assert d.allowed is False  # 公共数据但 Tier3 超额且内网全挂 → 拒绝


def test_admin_lock_rejected_if_violates_classification():
    # 管理员把敏感智能体锁到 Tier3 → 安全优先，拒绝
    d = R.route("身份证 110101199003078888", ALL_UP, locked_tier=Tier.EXTERNAL_API)
    assert d.allowed is False


# ===== D2 终稿：基于 compute_policy 的路由（分级仅告警，不否决路由） =====
from secureguard.compute_router import AgentComputePolicy


def test_policy_hr_agent_local_only():
    # HR助手仅 tier1；即便含 PII，路由仍按 policy，但产出审计告警
    pol = AgentComputePolicy(allowed_tiers=["tier1"])
    d = R.route_by_policy("员工身份证 110101199003078888", pol, ALL_UP)
    assert d.allowed and d.tier == Tier.LOCAL
    assert "pii_alert=True" in d.notes


def test_policy_general_agent_can_use_external():
    # 通用问答可用 tier3；非敏感内容正常走，无告警
    pol = AgentComputePolicy(allowed_tiers=["tier1", "tier2", "tier3"])
    status = {Tier.LOCAL: TierStatus(False), Tier.PRIVATE_CLOUD: TierStatus(False),
              Tier.EXTERNAL_API: TierStatus(True)}
    d = R.route_by_policy("什么是幂等性？", pol, status)
    assert d.allowed and d.tier == Tier.EXTERNAL_API


def test_policy_skip_tier2_order():
    # 代码助手 tier1+tier3 跳 tier2
    pol = AgentComputePolicy(allowed_tiers=["tier1", "tier3"], preferred_order=["tier1", "tier3"])
    status = {Tier.LOCAL: TierStatus(False), Tier.PRIVATE_CLOUD: TierStatus(True),
              Tier.EXTERNAL_API: TierStatus(True)}
    d = R.route_by_policy("写个排序", pol, status)
    assert d.allowed and d.tier == Tier.EXTERNAL_API  # 跳过 tier2 即便它在线


def test_policy_force_local_for_risk():
    pol = AgentComputePolicy(allowed_tiers=["tier1", "tier2"], force_local_for=["R0", "R1"])
    d = R.route_by_policy("敏感操作", pol, ALL_UP, risk_level="R1")
    assert d.allowed and d.tier == Tier.LOCAL


def test_policy_fail_closed_when_all_allowed_down():
    pol = AgentComputePolicy(allowed_tiers=["tier1", "tier2"], fail_strategy="closed")
    status = {Tier.LOCAL: TierStatus(False), Tier.PRIVATE_CLOUD: TierStatus(False)}
    d = R.route_by_policy("任意", pol, status)
    assert d.allowed is False


def test_classify_for_audit_only_alerts():
    a = R.classify_for_audit("密钥 sk-ABCDEFGHIJKLMNOP1234567890")
    assert a["pii_alert"] is True and a["severity"] == "high"
    b = R.classify_for_audit("什么是幂等性")
    assert b["pii_alert"] is False
