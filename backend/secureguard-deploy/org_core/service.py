"""
org_core.service — 操作入口(所有写操作必须过鉴权 + 落审计)。

业务代码只调 OrgService,不直接碰 repo。每个写操作:
  1) 取 caller 的 current_grant → authorize(动作, 目标节点)
  2) 通过才执行,并 write_audit(锚定真人+子账号)
  3) 越权 → 抛 PermissionDenied(显式失败),且照样审计(留痕未遂越权)
这一层把"管理员只能管子树""按子账号鉴权""全程审计"焊死在唯一入口。
"""
from __future__ import annotations

import uuid
from typing import Optional

from . import authz
from .audit import write_audit
from .models import (
    AdminScope, Grant, NodeType, OrgNode, PermissionDenied, Role, Tenant, User,
    UserKind, UserStatus,
)
from .permissions import P, validate_perm_keys
from .repository import Repos


class OrgService:
    def __init__(self, repo: Repos) -> None:
        self.repo = repo

    # ------------------------------------------------------------------ #
    # 内部:鉴权 + 审计 的统一闸
    # ------------------------------------------------------------------ #
    def _guard(self, tenant_id: str, caller_grant_id: str, action: str,
               target_node_id: Optional[str], target_desc: str) -> Grant:
        g = self.repo.get_grant(tenant_id, caller_grant_id)
        caller_user = g.user_id if g else "unknown"
        ok, reason = authz.authorize(self.repo, tenant_id, caller_grant_id, action, target_node_id)
        write_audit(self.repo, tenant_id=tenant_id, user_id=caller_user, grant_id=caller_grant_id,
                    action=action, target=target_desc, ok=ok, reason=reason)
        if not ok:
            raise PermissionDenied(reason)
        return g  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    # 租户 / 组织树(组织管理:沿子树)
    # ------------------------------------------------------------------ #
    def bootstrap_tenant(self, name: str, root_name: str) -> tuple[Tenant, OrgNode]:
        """开租户 + 建根节点。系统级操作(无 caller),用于初始化一个企业。"""
        t = Tenant(uuid.uuid4().hex, name)
        self.repo.add_tenant(t)
        root = OrgNode(uuid.uuid4().hex, t.id, None, NodeType.COMPANY, root_name)
        self.repo.add_node(root)
        return t, root

    def create_node(self, tenant_id: str, caller_grant_id: str, *,
                    parent_id: str, type: NodeType, name: str) -> OrgNode:
        # 目标是"在 parent 下建子节点" → 校 parent 在管理子树内
        self._guard(tenant_id, caller_grant_id, P.ORG_MANAGE, parent_id, f"create_node under {parent_id}")
        n = OrgNode(uuid.uuid4().hex, tenant_id, parent_id, type, name)
        self.repo.add_node(n)
        return n

    def rename_node(self, tenant_id: str, caller_grant_id: str, node_id: str, new_name: str) -> OrgNode:
        self._guard(tenant_id, caller_grant_id, P.ORG_MANAGE, node_id, f"rename {node_id}")
        n = self.repo.get_node(tenant_id, node_id)
        if not n:
            raise KeyError("节点不存在")
        n.name = new_name
        self.repo.update_node(n)
        return n

    def move_node(self, tenant_id: str, caller_grant_id: str, node_id: str, new_parent_id: str) -> OrgNode:
        """合并/拆分的原子操作:把子树挂到新父下。需对【源】和【目标父】都在管理子树内。"""
        self._guard(tenant_id, caller_grant_id, P.ORG_MANAGE, node_id, f"move {node_id}")
        # 额外校验目标父也在管理子树(防止把节点搬出自己的管辖)
        if not authz.in_admin_scope(self.repo, tenant_id, self._uid(tenant_id, caller_grant_id), new_parent_id):
            write_audit(self.repo, tenant_id=tenant_id, user_id=self._uid(tenant_id, caller_grant_id),
                        grant_id=caller_grant_id, action=P.ORG_MANAGE, target=f"move->{new_parent_id}",
                        ok=False, reason="目标父不在管理子树内")
            raise PermissionDenied("目标父节点不在你的管理子树内")
        n = self.repo.get_node(tenant_id, node_id)
        if not n:
            raise KeyError("节点不存在")
        n.parent_id = new_parent_id
        self.repo.update_node(n)
        return n

    # ------------------------------------------------------------------ #
    # 人员 / 岗位 / 子账号(用户与授权管理:沿子树)
    # ------------------------------------------------------------------ #
    def add_user(self, tenant_id: str, caller_grant_id: str, *, home_node_id: str,
                 kind: UserKind = UserKind.INTERNAL, display_name: str = "") -> User:
        """在某组织节点下建人 → 校该节点在管理子树内。"""
        self._guard(tenant_id, caller_grant_id, P.USER_MANAGE, home_node_id, f"add_user@{home_node_id}")
        u = User(uuid.uuid4().hex, tenant_id, kind, UserStatus.ACTIVE, display_name)
        self.repo.add_user(u)
        return u

    def disable_user(self, tenant_id: str, caller_grant_id: str, user_id: str, at_node_id: str) -> None:
        """离职关停:一刀停其所有子账号(grant)。"""
        self._guard(tenant_id, caller_grant_id, P.USER_MANAGE, at_node_id, f"disable_user {user_id}")
        self.repo.set_user_status(tenant_id, user_id, UserStatus.DISABLED.value)
        for g in self.repo.grants_of_user(tenant_id, user_id):
            self.repo.set_grant_active(tenant_id, g.id, False)

    def define_role(self, tenant_id: str, caller_grant_id: str, at_node_id: str,
                    name: str, perm_keys: frozenset[str]) -> Role:
        self._guard(tenant_id, caller_grant_id, P.ROLE_MANAGE, at_node_id, f"define_role {name}")
        r = Role(uuid.uuid4().hex, tenant_id, name, validate_perm_keys(perm_keys))
        self.repo.add_role(r)
        return r

    def grant_role(self, tenant_id: str, caller_grant_id: str, *, user_id: str, role_id: str,
                   org_node_id: str, label: str = "", is_default: bool = False) -> Grant:
        """派岗/建子账号:目标组织节点必须在管理子树内。"""
        self._guard(tenant_id, caller_grant_id, P.GRANT_MANAGE, org_node_id, f"grant {user_id}->{role_id}@{org_node_id}")
        g = Grant(uuid.uuid4().hex, tenant_id, user_id, role_id, org_node_id, label, True, is_default)
        self.repo.add_grant(g)
        return g

    def grant_admin_scope(self, tenant_id: str, caller_grant_id: str, *, user_id: str, org_node_id: str) -> AdminScope:
        """授予某人一个管理子树。需 caller 自己能管该子树(不能凭空造出超出自己范围的管理员)。"""
        self._guard(tenant_id, caller_grant_id, P.GRANT_MANAGE, org_node_id, f"admin_scope {user_id}@{org_node_id}")
        s = AdminScope(uuid.uuid4().hex, tenant_id, user_id, org_node_id)
        self.repo.add_admin_scope(s)
        return s

    # ------------------------------------------------------------------ #
    # 系统级初始化:任命第一个管理员(无 caller,仅 bootstrap 用)
    # ------------------------------------------------------------------ #
    def seed_admin(self, tenant_id: str, *, user: User, role: Role, node_id: str) -> tuple[Grant, AdminScope]:
        """初始化租户的首个管理员:建岗位、建子账号、授予全树管理子树。仅供 bootstrap。"""
        self.repo.add_user(user)
        self.repo.add_role(role)
        g = Grant(uuid.uuid4().hex, tenant_id, user.id, role.id, node_id, "初始管理员", True, True)
        self.repo.add_grant(g)
        s = AdminScope(uuid.uuid4().hex, tenant_id, user.id, node_id)
        self.repo.add_admin_scope(s)
        return g, s

    def _uid(self, tenant_id: str, grant_id: str) -> str:
        g = self.repo.get_grant(tenant_id, grant_id)
        return g.user_id if g else "unknown"
