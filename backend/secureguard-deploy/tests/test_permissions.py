"""tests/test_permissions.py — RBAC 权限引擎单测。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from secureguard.permissions import (
    Role, Visibility, AgentStatus, PermissionDenied,
    User, Agent, KnowledgeBase,
    can_create_agent, create_agent, submit_for_review, approve, reject,
    can_use_agent, can_access_kb, can_read_kb_content, can_manage_kb, can_manage_quota,
)

ADMIN = User("admin1", Role.ADMIN)
DEV = User("dev1", Role.DEVELOPER, dept_id="d1")
DEPT_ADMIN = User("da1", Role.DEPARTMENT_ADMIN, dept_id="d1")
USER_D1 = User("u1", Role.USER, dept_id="d1")
USER_D2 = User("u2", Role.USER, dept_id="d2")


# ---- 创建与可见性 ----
def test_user_can_create_private_agent_no_approval():
    a = create_agent(USER_D1, "ag1", Visibility.PRIVATE)
    assert a.status == AgentStatus.PUBLISHED and a.visibility == Visibility.PRIVATE


def test_user_cannot_create_public_agent():
    ok, _ = can_create_agent(USER_D1, Visibility.PUBLIC)
    assert ok is False
    try:
        create_agent(USER_D1, "ag2", Visibility.PUBLIC)
        assert False, "应抛 PermissionDenied"
    except PermissionDenied:
        pass


def test_developer_public_agent_starts_draft():
    a = create_agent(DEV, "ag3", Visibility.PUBLIC)
    assert a.status == AgentStatus.DRAFT


# ---- 发布状态机 ----
def test_publish_flow_requires_admin_approval():
    a = create_agent(DEV, "ag4", Visibility.PUBLIC)
    submit_for_review(DEV, a)
    assert a.status == AgentStatus.PENDING_REVIEW
    # developer 自己不能批
    try:
        approve(DEV, a); assert False
    except PermissionDenied:
        pass
    approve(ADMIN, a)
    assert a.status == AgentStatus.PUBLISHED


def test_reject_sends_back():
    a = create_agent(DEV, "ag5", Visibility.DEPARTMENT, dept_id="d1")
    submit_for_review(DEV, a)
    reject(ADMIN, a)
    assert a.status == AgentStatus.REJECTED
    # 打回后可再次提交
    submit_for_review(DEV, a)
    assert a.status == AgentStatus.PENDING_REVIEW


def test_dept_admin_cannot_approve_by_default():
    a = create_agent(DEV, "ag6", Visibility.DEPARTMENT, dept_id="d1")
    submit_for_review(DEV, a)
    try:
        approve(DEPT_ADMIN, a); assert False
    except PermissionDenied:
        pass  # 默认仅 admin 审批


# ---- 使用可见性 ----
def test_unpublished_agent_only_owner_sees():
    a = create_agent(DEV, "ag7", Visibility.PUBLIC)  # draft
    assert can_use_agent(DEV, a)[0] is True
    assert can_use_agent(USER_D1, a)[0] is False


def test_department_agent_limited_to_dept():
    a = create_agent(DEV, "ag8", Visibility.DEPARTMENT, dept_id="d1")
    submit_for_review(DEV, a); approve(ADMIN, a)
    assert can_use_agent(USER_D1, a)[0] is True    # 同部门
    assert can_use_agent(USER_D2, a)[0] is False   # 跨部门


def test_private_agent_only_owner():
    a = create_agent(DEV, "ag9", Visibility.PRIVATE)
    assert can_use_agent(DEV, a)[0] is True
    assert can_use_agent(USER_D1, a)[0] is False


# ---- 知识库隔离（D7） ----
def test_cannot_access_others_private_kb():
    kb = KnowledgeBase("kb1", Visibility.PRIVATE, owner_id="u1")
    assert can_access_kb(USER_D1, kb)[0] is True
    assert can_access_kb(USER_D2, kb)[0] is False


def test_department_kb_limited_to_dept():
    kb = KnowledgeBase("kb2", Visibility.DEPARTMENT, dept_id="d1")
    assert can_access_kb(USER_D1, kb)[0] is True
    assert can_access_kb(USER_D2, kb)[0] is False


def test_admin_cannot_read_private_kb_content():
    kb = KnowledgeBase("kb3", Visibility.PRIVATE, owner_id="u1")
    # admin 可管理但不可读原文（D7）
    assert can_read_kb_content(ADMIN, kb)[0] is False
    assert can_manage_kb(ADMIN, kb)[0] is True
    assert can_read_kb_content(USER_D1, kb)[0] is True  # owner 可读


def test_dept_admin_cannot_read_member_private_kb():
    kb = KnowledgeBase("kb4", Visibility.PRIVATE, owner_id="u1", dept_id="d1")
    assert can_read_kb_content(DEPT_ADMIN, kb)[0] is False


# ---- 配额 ----
def test_quota_management_scope():
    assert can_manage_quota(ADMIN, USER_D2)[0] is True
    assert can_manage_quota(DEPT_ADMIN, USER_D1)[0] is True    # 同部门
    assert can_manage_quota(DEPT_ADMIN, USER_D2)[0] is False   # 跨部门
    assert can_manage_quota(USER_D1, USER_D1)[0] is False      # 普通用户无权
