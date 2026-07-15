"""tests/test_l3_output_guard.py — L3 输出守卫单测。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from secureguard.l3_output_guard import OutputGuard

og = OutputGuard()


def test_redacts_openai_key():
    out = og.check("your key is sk-ABCDEFGHIJKLMNOPQRSTUVWX1234567890")
    assert "[OPENAI_KEY_REDACTED]" in out["sanitized_output"]
    assert out["safe"] is False  # 含敏感 → 不 safe（但已脱敏）


def test_redacts_multiple_formats():
    text = ("k1 ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 "
            "k2 AKIAIOSFODNN7EXAMPLE "
            "conn postgres://u:p@host:5432/db")
    out = og.check(text)
    s = out["sanitized_output"]
    assert "[GITHUB_TOKEN_REDACTED]" in s
    assert "[AWS_ACCESS_KEY_REDACTED]" in s
    assert "[DB_CONN_REDACTED]" in s


def test_hallucination_signal_flagged():
    out = og.check("I think this is probably correct, as far as I know.")
    labels = {i["type"] for i in out["issues"]}
    assert "hallucination_signal" in labels


def test_missing_citation_when_required():
    out = og.check("结论：营收增长。", {"require_citation": True})
    assert any(i["type"] == "missing_citation" for i in out["issues"])
    assert out["overall_pass"] is False


def test_clean_grounded_output_passes():
    out = og.check("营收增长 [doc_1]。成本下降 [doc_2]。", {"require_citation": True})
    assert out["safe"] is True and out["overall_pass"] is True
