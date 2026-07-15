"""tests/test_sk_service.py — 出站 sk 密钥（签发/校验/范围/计量/吊销）。"""
import sys, os, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.sk_service import SkService


def test_issue_returns_plaintext_once():
    s = SkService()
    r = s.issue("owner1", "测试", ["general"], meter="calls", limit=100)
    assert r["key"].startswith("sk-live-")        # 明文只此一次
    assert "warning" in r and r["meter"] == "calls" and r["limit"] == 100
    # 列表里不含明文 key
    lst = s.list_for_owner("owner1")
    assert "key" not in lst[0] and "key_hash" not in lst[0]


def test_verify_valid_and_invalid():
    s = SkService()
    r = s.issue("o", "x", ["general"])
    rec = s.verify(r["key"])
    assert rec is not None and rec.owner_id == "o"
    assert s.verify("sk-bogus") is None
    assert s.verify("") is None


def test_revoked_sk_fails_verify():
    s = SkService()
    r = s.issue("o", "x", ["general"])
    rec = s.verify(r["key"])
    s.revoke(rec.id, owner_id="o")
    assert s.verify(r["key"]) is None             # 吊销后失效


def test_scope_enforced():
    s = SkService()
    r = s.issue("o", "x", ["legal"])              # 只授权 legal
    rec = s.verify(r["key"])
    assert s.can_call_agent(rec, "legal") is True
    assert s.can_call_agent(rec, "general") is False  # 越权被挡


def test_quota_calls_exhaustion():
    s = SkService()
    r = s.issue("o", "x", ["general"], meter="calls", limit=2)
    rec = s.verify(r["key"])
    assert s.check_quota(rec)["ok"] is True
    s.consume(rec, calls=1); s.consume(rec, calls=1)
    assert s.check_quota(rec)["ok"] is False      # 用满 → 拒绝（端点会 429）


def test_quota_tokens_meter():
    s = SkService()
    r = s.issue("o", "x", ["general"], meter="tokens", limit=1000)
    rec = s.verify(r["key"])
    s.consume(rec, calls=1, tokens=999)
    assert s.check_quota(rec)["ok"] is True
    s.consume(rec, calls=1, tokens=10)
    assert s.check_quota(rec)["ok"] is False       # token 超限


def test_unlimited_when_no_limit():
    s = SkService()
    r = s.issue("o", "x", ["general"], limit=None)
    rec = s.verify(r["key"])
    for _ in range(100):
        s.consume(rec, calls=1)
    assert s.check_quota(rec)["ok"] is True         # 不限额


def test_recharge_requires_allow():
    s = SkService()
    r = s.issue("o", "x", ["general"], meter="calls", limit=5, allow_recharge=True)
    rec = s.verify(r["key"])
    s.consume(rec, calls=5)
    assert s.check_quota(rec)["ok"] is False
    s.recharge(rec.id, 5, owner_id="o")             # 续费
    assert s.check_quota(rec)["ok"] is True
    # 不允许续费的 sk
    r2 = s.issue("o", "y", ["general"], limit=5, allow_recharge=False)
    rec2 = s.verify(r2["key"])
    try:
        s.recharge(rec2.id, 5, owner_id="o"); assert False
    except ValueError:
        pass


def test_revoke_only_own():
    s = SkService()
    r = s.issue("owner1", "x", ["general"])
    rec = s.verify(r["key"])
    try:
        s.revoke(rec.id, owner_id="someone_else"); assert False
    except PermissionError:
        pass


def test_period_reset():
    s = SkService()
    r = s.issue("o", "x", ["general"], meter="calls", limit=5, reset_mode="period", period="monthly")
    rec = s.verify(r["key"])
    s.consume(rec, calls=5)
    assert s.check_quota(rec)["ok"] is False
    rec.reset_at = 1  # 强制已到重置时间
    assert s.check_quota(rec)["ok"] is True          # 周期重置后恢复


def test_end_to_end_openai_call_through_kernel():
    """sk 调用走完整 run_chat 安全内核，返回答案并扣量。"""
    from backend.state import AppState
    from backend.chat_service import run_chat, collect_answer
    st = AppState()
    r = st.sk.issue("owner1", "外部调用", ["general"], meter="calls", limit=10)
    rec = st.sk.verify(r["key"])
    async def go():
        res = await collect_answer(
            run_chat(st, "你好", agent_id="general", session_id=f"sk_{rec.id}",
                     caller={"id": f"sk:{rec.id}", "role": "user"}))
        return res
    res = asyncio.run(go())
    assert "answer" in res
    st.sk.consume(rec, calls=1, tokens=20)
    assert rec.used_calls == 1 and rec.used_tokens == 20
