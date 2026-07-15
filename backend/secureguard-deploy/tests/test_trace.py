"""tests/test_trace.py — D3 思考面板双轨单测。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from secureguard.trace import TraceFrame, build_public_trace, build_audit_trace, split_frame


def test_gate_frame_hides_rule_id_from_public():
    f = TraceFrame(stage="harness", type="gate", gate_result="BLOCK", rule_id="R-07", tier="tier1")
    pub = build_public_trace(f)
    aud = build_audit_trace(f)
    assert "R-07" not in str(pub)          # 用户看不到具体红线
    assert pub["status"] == "BLOCK" and "拦截" in pub["display"]
    assert aud["rule_id"] == "R-07"        # 审计保留


def test_tool_result_with_pii_is_redacted_in_public():
    f = TraceFrame(stage="tool", type="tool_call", tool_name="search_kb",
                   result="员工密钥 sk-ABCDEFGHIJKLMNOP1234567890 和更多内容", result_count=3)
    pub = build_public_trace(f)
    assert "sk-ABCDEFGHIJKLMNOP1234567890" not in str(pub)  # 已脱敏
    assert pub["params_redacted"] is False


def test_fully_redacted_result_shows_graceful_message():
    # 返回值全是敏感 → 面板不空白，显示"调用成功+计数+隐藏原因"
    f = TraceFrame(stage="tool", type="tool_call", tool_name="get_profile",
                   result="sk-ABCDEFGHIJKLMNOP1234567890", result_count=1)
    pub = build_public_trace(f)
    assert pub["result_hidden"] is True
    assert "调用完成" in pub["display"] and "隐藏" in pub["display"]
    assert pub["display"].strip() != ""    # 永不空白


def test_audit_trace_stores_hash_not_plaintext():
    secret = "员工身份证 110101199003078888"
    f = TraceFrame(stage="tool", type="tool_call", tool_name="x", result=secret)
    aud = build_audit_trace(f)
    assert secret not in str(aud) and len(aud["result_hash"]) == 64


def test_normal_tool_result_passes_through():
    f = TraceFrame(stage="tool", type="tool_call", tool_name="calc", result="结果是 42")
    pub = build_public_trace(f)
    assert pub["result_hidden"] is False and "42" in pub["result"]


def test_split_frame_returns_both_tracks():
    f = TraceFrame(stage="C4", type="route", summary="路由到 机电安装/暖通")
    both = split_frame(f, session_id="s1")
    assert "public" in both and "audit" in both
    assert both["audit"]["session_id"] == "s1"


def test_public_display_never_empty():
    f = TraceFrame(stage="C1", type="context_load", summary="")
    pub = build_public_trace(f)
    assert pub["display"].strip() != ""
