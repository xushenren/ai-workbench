"""tests/test_agent_service.py — B3 智能体 CRUD + 发布状态机单测。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.agent_service import AgentService
from secureguard.permissions import User, Role, Visibility, AgentStatus, PermissionDenied

ADMIN = User("u_admin", Role.ADMIN)
DEV = User("u_dev", Role.DEVELOPER, dept_id="d1")
DEPT_ADMIN = User("u_da", Role.DEPARTMENT_ADMIN, dept_id="d1")
USER1 = User("u1", Role.USER, dept_id="d1")
USER2 = User("u2", Role.USER, dept_id="d2")


def test_seed_has_three_published_public():
    s = AgentService()
    pub = [r for r in s._agents.values() if r["visibility"] == "public" and r["status"] == "published"]
    assert len(pub) == 3


def test_user_creates_private_published_immediately():
    s = AgentService()
    rec = s.create(USER1, {"name": "我的助手", "visibility": "private"})
    assert rec["status"] == AgentStatus.PUBLISHED.value
    assert rec["visibility"] == Visibility.PRIVATE.value and rec["owner_id"] == "u1"


def test_user_cannot_create_public():
    s = AgentService()
    try:
        s.create(USER1, {"name": "x", "visibility": "public"})
        assert False, "应抛 PermissionDenied"
    except PermissionDenied:
        pass


def test_developer_public_starts_draft():
    s = AgentService()
    rec = s.create(DEV, {"name": "团队助手", "visibility": "public"})
    assert rec["status"] == AgentStatus.DRAFT.value


def test_publish_flow_requires_admin():
    s = AgentService()
    rec = s.create(DEV, {"name": "团队助手", "visibility": "public"})
    aid = rec["id"]
    s.submit(DEV, aid)
    assert s.get(aid)["status"] == AgentStatus.PENDING_REVIEW.value
    # developer 自己不能批
    try:
        s.approve(DEV, aid); assert False
    except PermissionDenied:
        pass
    s.approve(ADMIN, aid)
    assert s.get(aid)["status"] == AgentStatus.PUBLISHED.value


def test_reject_then_resubmit():
    s = AgentService()
    rec = s.create(DEV, {"name": "x", "visibility": "department", "dept_id": "d1"})
    aid = rec["id"]
    s.submit(DEV, aid)
    s.reject(ADMIN, aid)
    assert s.get(aid)["status"] == AgentStatus.REJECTED.value
    s.submit(DEV, aid)
    assert s.get(aid)["status"] == AgentStatus.PENDING_REVIEW.value


def test_dept_admin_cannot_approve_by_default():
    s = AgentService()
    rec = s.create(DEV, {"name": "x", "visibility": "department", "dept_id": "d1"})
    s.submit(DEV, rec["id"])
    try:
        s.approve(DEPT_ADMIN, rec["id"]); assert False
    except PermissionDenied:
        pass


# ---------- 可见性过滤 ----------
def test_list_unpublished_only_owner_sees():
    s = AgentService()
    rec = s.create(DEV, {"name": "草稿", "visibility": "public"})  # draft
    dev_ids = {r["id"] for r in s.list_for(DEV)}
    user_ids = {r["id"] for r in s.list_for(USER1)}
    assert rec["id"] in dev_ids and rec["id"] not in user_ids


def test_list_department_agent_scoped():
    s = AgentService()
    rec = s.create(DEV, {"name": "部门", "visibility": "department", "dept_id": "d1"})
    s.submit(DEV, rec["id"]); s.approve(ADMIN, rec["id"])
    assert rec["id"] in {r["id"] for r in s.list_for(USER1)}   # 同部门
    assert rec["id"] not in {r["id"] for r in s.list_for(USER2)}  # 跨部门


def test_list_private_only_owner():
    s = AgentService()
    rec = s.create(USER1, {"name": "私人", "visibility": "private"})
    assert rec["id"] in {r["id"] for r in s.list_for(USER1)}
    assert rec["id"] not in {r["id"] for r in s.list_for(USER2)}


def test_anon_sees_only_published_public():
    s = AgentService()
    s.create(DEV, {"name": "草稿", "visibility": "public"})  # draft，匿名不可见
    ids = {r["id"] for r in s.list_for(None)}
    assert ids == {"general", "electromechanical", "code"}  # 只见三个已发布公共


def test_agent_endpoints_if_fastapi_available():
    """端点级测试：装了 fastapi 才跑（真机），沙箱自动跳过。"""
    try:
        from fastapi.testclient import TestClient  # type: ignore
        from backend.app import app, state
    except Exception:
        return
    if app is None:
        return
    client = TestClient(app)
    # 匿名列表只见公共已发布（>=3 防跨测试污染；精确隔离由 test_anon_sees_only_published_public 守）
    r = client.get("/v1/agents")
    assert r.status_code == 200 and len(r.json()) >= 3
    # developer 登录建公共智能体 → draft
    tok = state.auth.login("13800000001", "dev123")[0]
    h = {"Authorization": f"Bearer {tok}"}
    c = client.post("/v1/admin/agents", json={"name": "团队助手", "visibility": "public"}, headers=h)
    assert c.status_code == 200 and c.json()["status"] == "draft"
    aid = c.json()["id"]
    # 提交 → developer 批被拒(403) → admin 批通过
    client.post(f"/v1/admin/agents/{aid}/submit", headers=h)
    assert client.post(f"/v1/admin/agents/{aid}/approve", headers=h).status_code == 403
    atok = state.auth.login("13800000000", "admin123")[0]
    ah = {"Authorization": f"Bearer {atok}"}
    assert client.post(f"/v1/admin/agents/{aid}/approve", headers=ah).status_code == 200
    # 普通 user 不能建公共 → 403
    utok = state.auth.login("13800000003", "user123")[0]
    uh = {"Authorization": f"Bearer {utok}"}
    assert client.post("/v1/admin/agents", json={"name": "x", "visibility": "public"}, headers=uh).status_code == 403
