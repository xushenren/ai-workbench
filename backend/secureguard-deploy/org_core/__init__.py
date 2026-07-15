"""org_core — 组织/权限/多租户 底层内核(Python,SQLite/PG 双实现,无状态鉴权,审计)。"""
from .authz import authorize, in_admin_scope, is_descendant_or_self, resolve_grant
from .audit import verify_chain, write_audit
from .models import (
    AdminScope, AuditEntry, Grant, NodeType, OrgNode, PermissionDenied, Role,
    Tenant, User, UserKind, UserStatus, Visibility,
)
from .permissions import DEFAULT_ROLE_TEMPLATES, P, validate_perm_keys
from .repository import Repos
from .service import OrgService
from .sqlite_repo import SqliteRepos

__all__ = [
    "OrgService", "SqliteRepos", "Repos", "authorize", "in_admin_scope",
    "is_descendant_or_self", "resolve_grant", "write_audit", "verify_chain",
    "Tenant", "OrgNode", "User", "Role", "Grant", "AdminScope", "AuditEntry",
    "NodeType", "UserKind", "UserStatus", "Visibility", "PermissionDenied",
    "P", "DEFAULT_ROLE_TEMPLATES", "validate_perm_keys",
]
__version__ = "0.1.0"
