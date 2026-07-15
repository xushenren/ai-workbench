"""
org_core.authz — 无状态鉴权引擎(五条硬规则的执行点)。

纯函数式:输入 repo + 当前子账号(grant)+ 动作 + 目标节点,输出 (allowed, reason)。
不缓存状态 → 大公司多副本时每个副本独立鉴权(可水平扩展)。

五条硬规则:
  R1 租户隔离      所有读取按 tenant_id;跨租户对象一律不可见。
  R2 业务权限不继承 业务动作的 scope = grant.org_node 本身(不含后代)。
  R3 管理权限沿子树 管理动作要求目标 ∈ 操作者某条 admin_scope 的子树。
  R4 按当前子账号   权限/范围全取 current_grant,不取真人聚合。
  R5 审计锚定真人+子账号(由 service 落实)。
"""
from __future__ import annotations

from typing import Optional, Tuple

from .models import Grant, UserStatus
from .permissions import MANAGEMENT_PERMS
from .repository import Repos

Decision = Tuple[bool, str]


def is_descendant_or_self(repo: Repos, tenant_id: str, node_id: str, ancestor_id: str) -> bool:
    """node_id 是否 == ancestor_id 或在其子树内(沿 parent 链上溯)。"""
    cur: Optional[str] = node_id
    seen = set()  # 防环
    while cur is not None and cur not in seen:
        if cur == ancestor_id:
            return True
        seen.add(cur)
        n = repo.get_node(tenant_id, cur)
        cur = n.parent_id if n else None
    return False


def resolve_grant(repo: Repos, tenant_id: str, grant_id: str) -> Grant:
    """取当前子账号,校验:存在、属本租户、active、且真人未停用。否则显式失败。"""
    g = repo.get_grant(tenant_id, grant_id)
    if g is None:
        raise LookupError("子账号不存在或不属于本租户")
    if not g.active:
        raise PermissionError("该子账号(任职)已停用")
    u = repo.get_user(tenant_id, g.user_id)
    if u is None or u.status != UserStatus.ACTIVE:
        raise PermissionError("用户已离职/停用,所有任职失效")
    return g


def grant_perms(repo: Repos, g: Grant) -> frozenset[str]:
    role = repo.get_role(g.tenant_id, g.role_id)
    return role.perm_keys if role else frozenset()


def in_admin_scope(repo: Repos, tenant_id: str, user_id: str, target_node_id: str) -> bool:
    """目标节点是否落在该用户某条管理子树内(R3)。"""
    for s in repo.admin_scopes_of(tenant_id, user_id):
        if is_descendant_or_self(repo, tenant_id, target_node_id, s.org_node_id):
            return True
    return False


def authorize(
    repo: Repos,
    tenant_id: str,
    current_grant_id: str,
    action: str,
    target_node_id: Optional[str] = None,
) -> Decision:
    """一次请求的固定鉴权流程。target_node_id 为业务/管理操作的目标组织节点。"""
    try:
        g = resolve_grant(repo, tenant_id, current_grant_id)
    except (LookupError, PermissionError) as e:
        return False, str(e)

    perms = grant_perms(repo, g)
    if action not in perms:
        return False, f"岗位不具备权限位 {action}"

    # 管理动作:沿管理子树(R3);目标必须在操作者管理子树内
    if action in MANAGEMENT_PERMS:
        if target_node_id is None:
            return False, "管理操作必须指定目标组织节点"
        if not in_admin_scope(repo, tenant_id, g.user_id, target_node_id):
            return False, "目标不在你的管理子树内(不能管上级/平级)"
        return True, "ok(管理:子树内)"

    # 业务动作:不向下继承(R2);作用域 == 当前子账号所在节点
    if target_node_id is not None and target_node_id != g.org_node_id:
        return False, "业务权限不继承:仅在你当前任职所在的组织节点生效"
    return True, "ok(业务:本节点)"
