"""tests/test_restricted_admin_policy.py — 受限管理员护栏 + 可组合 Token 策略。"""
import sys, os, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.state import AppState
from backend.quota_service import QuotaService, QuotaPolicy
from secureguard.permissions import (
    User, Role, can_set_role, can_delete_user, can_manage_admins, can_manage_users,
    can_manage_kb, can_approve, KnowledgeBase, Visibility, Agent, AgentStatus, PermissionDenied,
)

ADMIN = User("u_admin", Role.ADMIN)
RADMIN = User("u_radmin", Role.RESTRICTED_ADMIN)
USER = User("u_user", Role.USER, dept_id="d1")
AUDITOR = User("u_auditor", Role.AUDITOR)


# ---------- 受限管理员护栏 ----------
def test_restricted_admin_can_manage_users():
    assert can_manage_users(RADMIN)[0] is True


def test_restricted_admin_cannot_create_admin():
    assert can_set_role(RADMIN, USER, Role.ADMIN)[0] is False
    assert can_set_role(RADMIN, USER, Role.RESTRICTED_ADMIN)[0] is False


def test_restricted_admin_cannot_appoint_auditor():
    assert can_set_role(RADMIN, USER, Role.AUDITOR)[0] is False
    assert can_set_role(ADMIN, USER, Role.AUDITOR)[0] is True  # 只有 admin 能任命审计员


def test_restricted_admin_cannot_touch_admin():
    assert can_set_role(RADMIN, ADMIN, Role.USER)[0] is False
    assert can_delete_user(RADMIN, ADMIN)[0] is False


def test_restricted_admin_cannot_delete_privileged():
    assert can_delete_user(RADMIN, AUDITOR)[0] is False
    assert can_delete_user(RADMIN, RADMIN)[0] is False
    assert can_delete_user(RADMIN, USER)[0] is True  # 普通用户可删


def test_only_admin_manages_admins():
    assert can_manage_admins(ADMIN)[0] is True
    assert can_manage_admins(RADMIN)[0] is False


def test_restricted_admin_cannot_see_private_content():
    from secureguard.permissions import can_audit_read_kb, can_read_kb_content
    kb = KnowledgeBase("k", Visibility.PRIVATE, owner_id="someone_else")
    assert can_audit_read_kb(RADMIN, kb)[0] is False   # 审计读取仅 auditor
    assert can_read_kb_content(RADMIN, kb)[0] is False  # 私有原文仅 owner


def test_restricted_admin_has_admin_subset_powers():
    """受限管理员能管 KB 生命周期、审批智能体（admin 子集）。"""
    kb = KnowledgeBase("k", Visibility.DEPARTMENT, dept_id="d1")
    assert can_manage_kb(RADMIN, kb)[0] is True
    ag = Agent("a", "owner", Visibility.PUBLIC, AgentStatus.PENDING_REVIEW)
    assert can_approve(RADMIN, ag)[0] is True


def test_service_set_role_enforces_guard():
    """端到端：受限管理员通过 service 改角色，护栏生效。"""
    st = AppState()
    # 受限管理员把普通用户提成 developer → 允许
    st.user_admin.set_role(RADMIN, "u_user", "developer")
    assert st.auth.get_user("u_user").role == Role.DEVELOPER
    # 受限管理员想造 admin → 被拒
    try:
        st.user_admin.set_role(RADMIN, "u_user", "admin"); assert False
    except PermissionDenied:
        pass


# ---------- 可组合 Token 策略 ----------
K = ("u1", "agX")


def test_policy_cooldown_auto_unlocks():
    clk = [1000.0]
    q = QuotaService(clock=lambda: clk[0])
    q.set_policy("agX", QuotaPolicy(reset_mode="cooldown", cooldown_seconds=7200))

    async def run():
        await q.consume(K, 1000, limit=1000)
        s1 = await q.status(K, limit=1000)
        clk[0] += 7201
        s2 = await q.status(K, limit=1000)
        return s1, s2

    s1, s2 = asyncio.run(run())
    assert s1["locked"] is True
    assert s2["locked"] is False and s2["used"] == 0


def test_policy_hardstop_blocks_recharge():
    q = QuotaService()
    q.set_policy("agX", QuotaPolicy(reset_mode="none", allow_recharge=False))

    async def run():
        await q.consume(K, 1000, limit=1000)
        return await q.recharge(K, 5000)

    r = asyncio.run(run())
    assert r["allowed"] is False and r["reason"] == "recharge_disabled"


def test_policy_hardstop_allows_paid_recharge():
    q = QuotaService()
    q.set_policy("agX", QuotaPolicy(reset_mode="none", allow_recharge=True))

    async def run():
        await q.consume(K, 1000, limit=1000)
        return await q.recharge(K, 5000)

    r = asyncio.run(run())
    assert r["allowed"] is True and r["locked"] is False


def test_policy_period_still_default():
    """无策略时回落周期模式（向后兼容）。"""
    q = QuotaService()

    async def run():
        await q.consume(K, 1000, limit=1000, freeze_period="monthly")
        return await q.status(K, limit=1000)

    s = asyncio.run(run())
    assert s["locked"] is True and s["freeze_until"] is not None  # 锁到下月


def test_restricted_admin_endpoints_if_fastapi_available():
    try:
        from fastapi.testclient import TestClient  # type: ignore
        from backend.app import app, state
    except Exception:
        return
    if app is None:
        return
    c = TestClient(app)
    rtok = state.auth.login("13800000005", "radmin123")[0]   # 受限管理员
    atok = state.auth.login("13800000000", "admin123")[0]
    RH = {"Authorization": f"Bearer {rtok}"}
    AH = {"Authorization": f"Bearer {atok}"}
    # 受限管理员能列用户
    assert c.get("/v1/admin/users", headers=RH).status_code == 200
    # 受限管理员造 admin → 403
    assert c.post("/v1/admin/users/u_user/role", json={"role": "admin"}, headers=RH).status_code == 403
    # 受限管理员任命审计员 → 403；admin 可以
    assert c.post("/v1/admin/users/u_dev/role", json={"role": "auditor"}, headers=RH).status_code == 403
    assert c.post("/v1/admin/users/u_dev/role", json={"role": "auditor"}, headers=AH).status_code == 200
    # 配额策略：admin/受限管理员可设
    pr = c.post("/v1/admin/quota/policy",
                json={"agent_id": "general", "reset_mode": "cooldown", "cooldown_seconds": 1800},
                headers=RH)
    assert pr.status_code == 200 and pr.json()["policy"]["reset_mode"] == "cooldown"
