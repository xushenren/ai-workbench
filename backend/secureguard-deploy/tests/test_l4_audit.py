"""tests/test_l4_audit.py — L4 审计单测。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from secureguard.l4_audit import AuditLogger, AuditEntry
from secureguard.types import Conflict, Rule, GateResult, Token


def test_no_plaintext_only_hash():
    a = AuditLogger()
    secret = "super-secret-input"
    a.log_stage(stage="L0", decision="PASS", raw_input=secret)
    e = a.entries[-1]
    # 不得存原文；只存 64 位 sha256 摘要
    assert secret not in e.input_hash
    assert len(e.input_hash) == 64


def test_conflict_recorded():
    a = AuditLogger()
    r1 = Rule("PROD_INTEGRITY", "irreversible", GateResult(Token.BLOCK))
    r2 = Rule("COMM_ETIQUETTE", "quiet hours", GateResult(Token.BLOCK))
    c = Conflict(rules=[r1, r2])
    a.record_conflict(c, c.winner())
    assert len(a.conflicts) == 1
    assert a.conflicts[0]["winner"][0] == "PROD_INTEGRITY"


def test_redline_hit_recorded():
    a = AuditLogger()
    a.note_redline("R-01", {"type": "drop_table"})
    assert len(a.redline_hits) == 1 and a.redline_hits[0]["redline_id"] == "R-01"


def test_summary_counts():
    a = AuditLogger()
    a.log_stage(stage="L1", decision="PASS")
    a.log_stage(stage="L1", decision="BLOCK")
    s = a.summary()
    assert s["total_entries"] == 2 and s["decisions"]["BLOCK"] == 1


def test_jsonl_persistence(tmp_path=None):
    import tempfile, json, os as _os
    d = tempfile.mkdtemp()
    path = _os.path.join(d, "audit.jsonl")
    a = AuditLogger(path=path)
    a.log_stage(stage="L4", decision="PASS", latency_ms=42)
    with open(path, encoding="utf-8") as f:
        line = json.loads(f.readline())
    assert line["stage"] == "L4" and line["latency_ms"] == 42
