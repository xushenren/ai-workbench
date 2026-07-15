"""tests/test_l1_gate.py — L1 仲裁门控单测。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from secureguard.l1_gate import gate, arbitrate, self_monitor, REDLINES
from secureguard.types import Token, Conflict, Rule, GateResult


def test_all_12_redlines_present():
    # 原 12 条红线 R-01..R-12 仍须存在（现已扩至 19）
    assert {f"R-{i:02d}" for i in range(1, 13)} <= set(REDLINES.keys())


def test_redline_drop_table_blocks():
    res = gate({"type": "drop_table", "backup_confirmed": False}, {})
    assert res.token == Token.BLOCK and res.notify and "R-01" in res.reason


def test_redline_skip_test_to_pass_ci_blocks():
    res = gate({"type": "skip_test", "reason": "to_pass_ci"}, {})
    assert res.token == Token.BLOCK and "R-05" in res.reason


def test_redline_force_push_main_blocks():
    res = gate({"type": "force_push", "branch": "main"}, {})
    assert res.token == Token.BLOCK and "R-02" in res.reason


def test_r2_escalates():
    res = gate({"type": "deploy", "risk_level": "R2", "r2_reason": "prod deploy"}, {})
    assert res.token == Token.ESCALATE


def test_self_monitor_block():
    res = self_monitor("这个测试明显没问题，先 skip 掉")
    assert res is not None and res.token == Token.BLOCK


def test_self_monitor_ask():
    res = self_monitor("端口应该是默认值吧")
    assert res is not None and res.token == Token.ASK


def test_domain_guard_software_missing_rollback():
    res = gate({"type": "deploy", "mutates_state": True, "domain": "software",
                "idempotency": True, "rollback_plan": False}, {})
    assert res.token == Token.BLOCK and "回滚" in res.reason


def test_domain_guard_dataml_eval_default_fail():
    res = gate({"type": "deploy_model", "domain": "data_ml", "eval_passed": False}, {})
    assert res.token == Token.BLOCK and "评估门" in res.reason


def test_normal_query_passes():
    res = gate({"type": "query", "risk_level": "R0", "domain": "general"}, {})
    assert res.token == Token.PASS


def test_arbitrate_safety_wins_over_etiquette():
    # 3am 场景：不可逆未确认(安全侧) × 静默时段(礼仪) → 安全侧 BLOCK
    res = gate(
        {"type": "query", "domain": "general"},
        {"irreversible_unconfirmed": True, "quiet_hours": True, "is_emergency": True},
    )
    assert res.token == Token.BLOCK and res.tier == "PROD_INTEGRITY"


def test_arbitrate_etiquette_yields_to_emergency_when_no_safety():
    # 仅礼仪 × 紧急（无安全侧规则）→ 礼仪让步 PASS
    res = gate(
        {"type": "query", "domain": "general"},
        {"quiet_hours": True, "velocity_pressure": True, "is_emergency": True},
    )
    assert res.token == Token.PASS


# ===== D1：19 红线 / 18 自省 + 新红线触发 =====
from secureguard.l1_gate import SELF_MONITOR_TRIGGERS


def test_19_redlines_18_self_monitor():
    assert len(REDLINES) == 19
    assert set(REDLINES.keys()) == {f"R-{i:02d}" for i in range(1, 20)}
    assert len(SELF_MONITOR_TRIGGERS) == 18


def test_r13_cross_tenant_blocks():
    res = gate({"type": "access_kb", "visibility": "private",
                "owner_id": "bob", "caller_id": "alice"}, {})
    assert res.token == Token.BLOCK and "R-13" in res.reason


def test_r14_sensitive_external_blocks():
    res = gate({"type": "route", "data_class": "RESTRICTED", "destination": "external"}, {})
    assert res.token == Token.BLOCK and "R-14" in res.reason


def test_r16_unmasked_pii_blocks():
    res = gate({"contains_unmasked_pii": True, "sink": "trace_panel"}, {})
    assert res.token == Token.BLOCK and "R-16" in res.reason
