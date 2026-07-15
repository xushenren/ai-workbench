"""tests/test_quota.py — B4 配额服务单测（纯 asyncio）。"""
import sys, os, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.quota_service import QuotaService, _next_month_first
from backend.state import AppState
from backend.chat_service import run_chat


K = ("u1", "general")


def test_consume_decrements_remaining():
    q = QuotaService()
    r = asyncio.run(q.consume(K, 100, limit=1000))
    assert r.allowed and r.used == 100 and r.remaining == 900 and not r.locked


def test_atomic_no_lost_updates():
    """并发扣减不丢更新——有锁则 used 精确等于总和（无锁会透支）。"""
    q = QuotaService()

    async def run():
        await asyncio.gather(*[q.consume(K, 1, limit=10_000) for _ in range(50)])
        return await q.status(K, limit=10_000)

    st = asyncio.run(run())
    assert st["used"] == 50  # 精确，无竞态丢失


def test_allow_negative_then_lock():
    """跨过阈值的请求照常完成(allowed=True)，之后锁定；下次请求被拒。"""
    q = QuotaService()

    async def run():
        r1 = await q.consume(K, 950, limit=1000)     # 未到顶
        r2 = await q.consume(K, 100, limit=1000)     # 1050 ≥ 1000 → 完成但锁定
        r3 = await q.consume(K, 1, limit=1000)       # 已锁 → 拒绝
        return r1, r2, r3

    r1, r2, r3 = asyncio.run(run())
    assert r1.allowed and not r1.locked
    assert r2.allowed and r2.locked            # 当前请求不中断，但触发锁定
    assert (not r3.allowed) and r3.reason == "quota_locked"


def test_recharge_unlocks_immediately():
    q = QuotaService()

    async def run():
        await q.consume(K, 1000, limit=1000)         # 锁定
        before = await q.status(K, limit=1000)
        await q.recharge(K, 5000)                     # 充值 → 立即解锁
        r = await q.consume(K, 1, limit=1000)
        return before, r

    before, r = asyncio.run(run())
    assert before["locked"] is True
    assert r.allowed and not r.locked


def test_set_limit_locks_if_below_used():
    q = QuotaService()

    async def run():
        await q.consume(K, 800, limit=1000)
        return await q.set_limit(K, 500)              # 新额度低于已用 → 锁定

    res = asyncio.run(run())
    assert res["locked"] is True


def test_freeze_reset_via_injected_clock():
    """到了冻结重置点(下月)→ 清零解锁。"""
    now = [1_700_000_000.0]  # 可变时钟
    q = QuotaService(clock=lambda: now[0])

    async def run():
        await q.consume(K, 1000, limit=1000, freeze_period="monthly")  # 锁定，freeze_until=下月1日
        locked = await q.status(K, limit=1000)
        now[0] = _next_month_first(now[0]) + 10        # 跳到下月之后
        after = await q.status(K, limit=1000)
        return locked, after

    locked, after = asyncio.run(run())
    assert locked["locked"] is True
    assert after["locked"] is False and after["used"] == 0  # 已重置


# ---------- 对话集成 ----------
def test_chat_blocks_when_quota_locked():
    st = AppState()
    caller = {"id": "u1", "role": "user", "dept_id": "d1"}

    async def run():
        # 先把该用户在 general 上的额度耗尽并锁定
        free = int(st.agent_service.get("general")["free_quota_tokens"])
        await st.quota.consume(("u1", "general"), free, limit=free)
        # 再发对话 → 应被配额拦截
        return [ev async for ev in run_chat(st, "你好", agent_id="general", caller=caller)]

    evs = asyncio.run(run())
    assert evs[-1]["blocked"] is True and evs[-1].get("reason") == "quota_locked"
    assert any("额度已用尽" in e.get("frame", {}).get("display", "") for e in evs)


def test_chat_anon_not_metered():
    st = AppState()

    async def run():
        return [ev async for ev in run_chat(st, "解释幂等性", agent_id="general", caller=None)]

    evs = asyncio.run(run())
    assert evs[-1]["blocked"] is False  # 匿名不计量，正常放行


def test_quota_endpoints_if_fastapi_available():
    """端点级测试：装了 fastapi 才跑（真机），沙箱自动跳过。"""
    try:
        from fastapi.testclient import TestClient  # type: ignore
        from backend.app import app, state
    except Exception:
        return
    if app is None:
        return
    client = TestClient(app)
    utok = state.auth.login("13800000003", "user123")[0]   # 普通 user
    uh = {"Authorization": f"Bearer {utok}"}
    # 查自己配额
    r = client.get("/v1/quota/general", headers=uh)
    assert r.status_code == 200 and "remaining" in r.json()
    # 充值
    rc = client.post("/v1/quota/general/recharge?add_tokens=5000", headers=uh)
    assert rc.status_code == 200 and rc.json()["locked"] is False
    # 普通 user 调别人配额 → 403（无管理权）
    adj = client.post("/v1/admin/quota",
                      json={"user_id": "u_dev", "agent_id": "general", "limit": 1},
                      headers=uh)
    assert adj.status_code == 403
    # admin 调配额 → 200
    atok = state.auth.login("13800000000", "admin123")[0]
    ah = {"Authorization": f"Bearer {atok}"}
    adj2 = client.post("/v1/admin/quota",
                       json={"user_id": "u_user", "agent_id": "general", "limit": 50000},
                       headers=ah)
    assert adj2.status_code == 200
