"""backend.audit_appointment_guard — #7:审计员任命只允许平台管理员。

规则:任命/派发"审计员"岗位,调用者必须是平台管理员(拥有全局管理权),
普通组织管理员(仅子树 GRANT_MANAGE)不可任命审计员——保证审计独立性。
在 org grant 端点里调用 guard 即可。
"""
from __future__ import annotations

AUDITOR_ROLE_NAMES = {"审计员", "auditor"}


def is_platform_admin(repo, tenant_id: str, person_id: str, root_node_id: str) -> bool:
    """平台管理员 = 管理子树覆盖组织根(能管全树)。"""
    from org_core.authz import in_admin_scope
    return in_admin_scope(repo, tenant_id, person_id, root_node_id)


def guard_appoint(repo, tenant_id: str, caller_person_id: str, root_node_id: str,
                  target_role_name: str) -> None:
    """若任命审计员但调用者非平台管理员 → 抛 PermissionError。"""
    if target_role_name in AUDITOR_ROLE_NAMES:
        if not is_platform_admin(repo, tenant_id, caller_person_id, root_node_id):
            raise PermissionError("仅平台管理员可任命审计员(保证审计独立性)")
