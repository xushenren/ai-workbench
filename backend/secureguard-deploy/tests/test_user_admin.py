"""tests/test_user_admin.py — 用户管理 + 部门申请 + 受控审计读取。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.state import AppState
from backend.user_admin_service import UserAdminService
from backend.kb_service import KBService
from secureguard import AuditLogger
from secureguard.permissions import User, Role, PermissionDenied, can_audit_read_kb, KnowledgeBase, Visibility

ADMIN = User("u_admin", Role.ADMIN)
USER = User("u_user", Role.USER, dept_id=None)
AUDITOR = User("u_auditor", Role.AUDITOR)


# ---------- 用户管理 ----------
def test_admin_lists_users():
    st = AppState()
    users = st.user_admin.list_users(ADMIN)
    assert any(u["id"] == "u_admin" for u in users)


def test_non_admin_cannot_list_users():
    st = AppState()
    try:
        st.user_admin.list_users(USER); assert False
    except PermissionDenied:
        pass


def test_admin_assigns_department_unblocks_dept_kb():
    """核心：给无部门用户分配部门后，他立刻能访问该部门知识库。"""
    st = AppState()
    # 注册一个无部门新用户
    tok, _ = st.auth.register_self("13911112222", "secret6")
    u = st.auth.resolve(tok)
    assert u.dept_id is None
    # 分配前：知识库列表只有公共
    kbs_before = {k["id"] for k in st.kb_service.list_for(u)}
    assert kbs_before == {"kb_std"}
    # admin 分配到 d1
    st.user_admin.assign_department(ADMIN, u.id, "d1")
    u2 = st.auth.get_user(u.id)  # 重新解析，部门已变
    kbs_after = {k["id"] for k in st.kb_service.list_for(u2)}
    assert "kb_dept" in kbs_after  # 现在能看到部门库


def test_admin_change_role():
    st = AppState()
    st.user_admin.set_role(ADMIN, "u_user", "developer")
    assert st.auth.get_user("u_user").role == Role.DEVELOPER


def test_user_cannot_change_roles():
    st = AppState()
    try:
        st.user_admin.set_role(USER, "u_admin", "user"); assert False
    except PermissionDenied:
        pass


# ---------- 部门申请 ----------
def test_request_department_does_not_grant_until_approved():
    st = AppState()
    tok, _ = st.auth.register_self("13933334444", "secret6")
    u = st.auth.resolve(tok)
    req = st.user_admin.request_department(u, "d1")
    # 申请未批准：部门仍为空
    assert st.auth.get_user(u.id).dept_id is None
    # admin 批准 → 部门生效
    st.user_admin.approve_request(ADMIN, req["id"])
    assert st.auth.get_user(u.id).dept_id == "d1"


def test_reject_request_keeps_no_department():
    st = AppState()
    tok, _ = st.auth.register_self("13955556666", "secret6")
    u = st.auth.resolve(tok)
    req = st.user_admin.request_department(u, "d1")
    st.user_admin.reject_request(ADMIN, req["id"])
    assert st.auth.get_user(u.id).dept_id is None


# ---------- 受控审计读取（职责分离 + 留痕） ----------
def test_admin_cannot_audit_read():
    """admin 没有审计读取权（职责分离）。"""
    kb = KnowledgeBase("kb_user2", Visibility.PRIVATE, owner_id="u2", dept_id="d2")
    assert can_audit_read_kb(ADMIN, kb)[0] is False
    assert can_audit_read_kb(AUDITOR, kb)[0] is True


def test_daily_search_isolation_unbroken_for_admin():
    """日常路径不变：admin 走普通检索仍看不到他人私有库。"""
    kb = KBService()
    res = kb.search(ADMIN, "u2 的私有内容")
    assert all(h["kb_id"] != "kb_user2" for h in res["results"])
    assert "kb_user2" not in res["accessible_kbs"]


def test_auditor_can_audit_read_others_private_and_it_is_logged():
    """审计员能读他人私有库原文，且产生一条不可篡改的审计记录。"""
    kb = KBService()
    log = AuditLogger()
    before = len(log.entries)
    out = kb.audit_read(AUDITOR, "kb_user2", reason="合规抽查 2026Q2", auditor_log=log)
    assert out["audited"] and out["owner_id"] == "u2"
    assert any("私有内容" in d["content"] for d in out["documents"])  # 确实读到了原文
    # 留痕：审计链多了一条，且记录了 reason 与目标
    assert len(log.entries) == before + 1
    e = log.entries[-1]
    assert e.stage == "AUDIT_READ" and "合规抽查" in e.reason
    # 审计链完整（不可篡改）
    assert log.verify_chain()["ok"] is True


def test_auditor_read_requires_reason():
    kb = KBService()
    log = AuditLogger()
    try:
        kb.audit_read(AUDITOR, "kb_user2", reason="  ", auditor_log=log); assert False
    except ValueError:
        pass


def test_non_auditor_audit_read_denied():
    kb = KBService()
    log = AuditLogger()
    try:
        kb.audit_read(ADMIN, "kb_user2", reason="x", auditor_log=log); assert False
    except PermissionDenied:
        pass


def test_user_admin_endpoints_if_fastapi_available():
    """端点级测试：装了 fastapi 才跑（真机），沙箱自动跳过。"""
    try:
        from fastapi.testclient import TestClient  # type: ignore
        from backend.app import app, state
    except Exception:
        return
    if app is None:
        return
    c = TestClient(app)
    atok = state.auth.login("13800000000", "admin123")[0]
    autok = state.auth.login("13800000004", "audit123")[0]
    utok = state.auth.login("13800000003", "user123")[0]
    AH = {"Authorization": f"Bearer {atok}"}
    AUH = {"Authorization": f"Bearer {autok}"}
    UH = {"Authorization": f"Bearer {utok}"}
    # admin 列用户；user 不能
    assert c.get("/v1/admin/users", headers=AH).status_code == 200
    assert c.get("/v1/admin/users", headers=UH).status_code == 403
    # 日常检索：admin 仍看不到 kb_user2
    s = c.post("/v1/kb/search", json={"query": "u2 的私有内容"}, headers=AH).json()
    assert "kb_user2" not in s.get("accessible_kbs", [])
    # 审计端点：user/admin 无权，auditor 可
    assert c.get("/v1/audit/kb/list", headers=UH).status_code == 403
    assert c.get("/v1/audit/kb/list", headers=AH).status_code == 403
    assert c.get("/v1/audit/kb/list", headers=AUH).status_code == 200
    # 审计读取：缺 reason → 400；带 reason → 200 + 留痕
    assert c.post("/v1/audit/kb/read", json={"kb_id": "kb_user2", "reason": ""}, headers=AUH).status_code == 400
    r = c.post("/v1/audit/kb/read", json={"kb_id": "kb_user2", "reason": "合规抽查"}, headers=AUH)
    assert r.status_code == 200 and r.json()["audited"] is True
