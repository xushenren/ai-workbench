"""tests/test_proxy_and_rotation.py — fail-closed 代理 + 审计轮转单测。"""
import sys, os, asyncio, tempfile, shutil
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from secureguard.safety_proxy import SafetyProxy, ProxyConfig
from secureguard.audit_rotation import RotatingAuditLogger
from secureguard.l4_audit import AuditEntry


class _GoodOrch:
    async def process(self, *a, **k):
        return {"blocked": False, "answer": "ok"}


class _BoomOrch:
    async def process(self, *a, **k):
        raise RuntimeError("guard exploded")


class _SlowOrch:
    async def process(self, *a, **k):
        await asyncio.sleep(1.0)
        return {"blocked": False}


def test_fail_closed_blocks_on_error():
    p = SafetyProxy(_BoomOrch(), ProxyConfig(fail_policy="closed"))
    res = asyncio.run(p.process("hi"))
    assert res["blocked"] is True and res["degraded"] is True


def test_fail_open_passes_on_error_when_explicit():
    p = SafetyProxy(_BoomOrch(), ProxyConfig(fail_policy="open"))
    res = asyncio.run(p.process("hi"))
    assert res["blocked"] is False and res["degraded"] is True


def test_timeout_fails_closed():
    p = SafetyProxy(_SlowOrch(), ProxyConfig(timeout_s=0.05, fail_policy="closed"))
    res = asyncio.run(p.process("hi"))
    assert res["blocked"] is True and res["stage"] == "timeout"


def test_circuit_breaker_opens_after_threshold():
    p = SafetyProxy(_BoomOrch(), ProxyConfig(breaker_threshold=3, breaker_cooldown_s=999))
    for _ in range(3):
        asyncio.run(p.process("hi"))
    # 第 4 次应被断路器短路
    res = asyncio.run(p.process("hi"))
    assert res["stage"] == "breaker_open"


def test_breaker_recovers_on_success():
    p = SafetyProxy(_GoodOrch(), ProxyConfig())
    res = asyncio.run(p.process("hi"))
    assert res["blocked"] is False and p.breaker.state == "closed"


def test_audit_rotation_by_size():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "audit.jsonl")
    log = RotatingAuditLogger(path, max_bytes=300, backup_count=3, retention_days=None)
    for i in range(50):
        log.log(AuditEntry(stage="L4", decision="PASS", reason="x" * 20))
    # 应产生至少一个轮转分卷
    assert os.path.exists(path + ".1")
    shutil.rmtree(d)
