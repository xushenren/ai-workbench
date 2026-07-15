"""tests/test_permission_matrix.py — 集中权限矩阵。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from secureguard.permissions import Role
from backend.permission_matrix import (
    can, capabilities_of, build_handbook,
    CAP_MANAGE_ADMINS, CAP_CONFIG_MODEL, CAP_ISSUE_SK, CAP_CREATE_AGENT,
    CAP_SHARE_GLOBAL, CAP_AUDIT_READ, CAP_USE_PLATFORM, CAP_MANAGE_USERS,
)


def test_only_admin_manages_admins():
    assert can(Role.ADMIN, CAP_MANAGE_ADMINS)
    for r in (Role.RESTRICTED_ADMIN, Role.DEVELOPER, Role.USER, Role.AUDITOR, Role.DEPARTMENT_ADMIN):
        assert not can(r, CAP_MANAGE_ADMINS)


def test_only_admin_configs_model():
    assert can(Role.ADMIN, CAP_CONFIG_MODEL)
    for r in (Role.RESTRICTED_ADMIN, Role.DEVELOPER, Role.USER, Role.AUDITOR):
        assert not can(r, CAP_CONFIG_MODEL)


def test_only_admin_issues_sk():
    assert can(Role.ADMIN, CAP_ISSUE_SK)
    for r in (Role.DEVELOPER, Role.USER, Role.RESTRICTED_ADMIN, Role.AUDITOR):
        assert not can(r, CAP_ISSUE_SK)


def test_developer_and_admin_create_agent():
    assert can(Role.ADMIN, CAP_CREATE_AGENT) and can(Role.DEVELOPER, CAP_CREATE_AGENT)
    assert not can(Role.USER, CAP_CREATE_AGENT)        # user 只能私有
    assert not can(Role.RESTRICTED_ADMIN, CAP_CREATE_AGENT)  # 受限管理员不管事


def test_restricted_admin_manages_users_not_admins():
    assert can(Role.RESTRICTED_ADMIN, CAP_MANAGE_USERS)
    assert not can(Role.RESTRICTED_ADMIN, CAP_MANAGE_ADMINS)


def test_share_global_dev_and_admin_only():
    assert can(Role.ADMIN, CAP_SHARE_GLOBAL) and can(Role.DEVELOPER, CAP_SHARE_GLOBAL)
    assert not can(Role.USER, CAP_SHARE_GLOBAL)


def test_audit_read_admin_and_auditor():
    assert can(Role.AUDITOR, CAP_AUDIT_READ) and can(Role.ADMIN, CAP_AUDIT_READ)
    assert not can(Role.USER, CAP_AUDIT_READ)


def test_everyone_uses_platform():
    for r in Role:
        assert can(r, CAP_USE_PLATFORM)


def test_capabilities_of_user_is_minimal():
    caps = capabilities_of(Role.USER)
    assert CAP_USE_PLATFORM in caps
    assert CAP_CONFIG_MODEL not in caps and CAP_ISSUE_SK not in caps


def test_handbook_matches_matrix():
    """说明书与矩阵同源：随机抽查几格一致。"""
    hb = build_handbook()
    assert len(hb["roles"]) == 6
    cfg = next(c for c in hb["capabilities"] if c["id"] == CAP_CONFIG_MODEL)
    assert cfg["roles"]["admin"] is True and cfg["roles"]["developer"] is False
    sk = next(c for c in hb["capabilities"] if c["id"] == CAP_ISSUE_SK)
    assert sk["roles"]["admin"] is True and sk["roles"]["user"] is False
