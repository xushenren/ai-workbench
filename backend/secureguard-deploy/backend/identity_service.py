"""
backend.identity_service — 身份桥接(org_core 成为新能力的身份权威)。

没有存量用户/数据 → 不搞双系统并存,直接让 org_core 当权威:
  - auth 仍管登录(手机号/密码/token);
  - 登录后,把该用户**惰性映射**到 org_core 的「真人 person + 默认 grant(子账号)」;
  - 老端点继续用 auth 的扁平 User(零改动);新端点用 get_caller_grant 拿 (tenant, grant)。

老 role → org_core 岗位 的默认映射在下方,可按需调整。单租户默认(t_default)。
纯 stdlib + org_core,可离线测。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from org_core import (
    OrgService, SqliteRepos, NodeType, User as OUser, UserKind, UserStatus, Role,
    DEFAULT_ROLE_TEMPLATES,
)
from org_core import OrgNode

# 老 role → (org_core 岗位模板名, 是否授予全树管理子树)
ROLE_TO_TEMPLATE: Dict[str, Tuple[str, bool]] = {
    "admin": ("平台管理员", True),
    "restricted_admin": ("组织管理员", True),
    "department_admin": ("组织管理员", False),   # 管理子树=其部门节点
    "developer": ("开发者", False),
    "user": ("成员", False),
    "auditor": ("审计员", False),
}
DEFAULT_TEMPLATE = ("成员", False)


@dataclass
class CallerIdentity:
    user_id: str
    tenant_id: str
    person_id: str
    grant_id: str
    role: str          # 老 role(透传,兼容)
    dept_id: Optional[str]


class IdentityService:
    """把 auth 用户桥接到 org_core。org_core 是组织/权限权威。"""

    def __init__(self, auth, org_repo=None) -> None:
        self.auth = auth
        self.repo = org_repo or SqliteRepos()        # 生产传持久化路径
        self.svc = OrgService(self.repo)
        self._map: Dict[str, CallerIdentity] = {}     # user_id -> identity
        self._roles: Dict[str, str] = {}              # 模板名 -> role_id(缓存)
        self._depts: Dict[str, str] = {}              # dept_id -> org_node_id(缓存)
        self.tenant_id, self.root_id = self._bootstrap()

    def _bootstrap(self) -> Tuple[str, str]:
        # 单租户默认 + 根节点(幂等:已存在则复用)
        t = self.repo.get_tenant("t_default")
        if t is None:
            self.repo.add_tenant(__import__("org_core").Tenant("t_default", "默认企业"))
            root = OrgNode("n_root", "t_default", None, NodeType.COMPANY, "总部")
            self.repo.add_node(root)
            return "t_default", "n_root"
        return "t_default", "n_root"

    def _role_for(self, template_name: str) -> str:
        if template_name in self._roles:
            return self._roles[template_name]
        perms = DEFAULT_ROLE_TEMPLATES.get(template_name, DEFAULT_ROLE_TEMPLATES["成员"])
        r = Role(uuid.uuid4().hex, self.tenant_id, template_name, perms)
        self.repo.add_role(r)
        self._roles[template_name] = r.id
        return r.id

    def _node_for_dept(self, dept_id: Optional[str]) -> str:
        if not dept_id:
            return self.root_id
        if dept_id in self._depts:
            return self._depts[dept_id]
        node = OrgNode("n_" + dept_id, self.tenant_id, self.root_id, NodeType.DEPARTMENT, dept_id)
        self.repo.add_node(node)
        self._depts[dept_id] = node.id
        return node.id

    def ensure(self, user_id: str, role: str = "user", dept_id: Optional[str] = None) -> CallerIdentity:
        """惰性映射:首次见到某用户时,在 org_core 建 person + 默认 grant。幂等。"""
        if user_id in self._map:
            return self._map[user_id]

        person = OUser(uuid.uuid4().hex, self.tenant_id, UserKind.INTERNAL, UserStatus.ACTIVE, user_id)
        self.repo.add_user(person)

        tmpl, whole_tree = ROLE_TO_TEMPLATE.get(role, DEFAULT_TEMPLATE)
        role_id = self._role_for(tmpl)
        node_id = self._node_for_dept(dept_id)

        grant = __import__("org_core").Grant(
            uuid.uuid4().hex, self.tenant_id, person.id, role_id, node_id,
            label=f"{user_id}@{tmpl}", active=True, is_default=True)
        self.repo.add_grant(grant)

        # 管理子树:admin→全树;department_admin→其部门节点
        if whole_tree:
            self.repo.add_admin_scope(__import__("org_core").AdminScope(
                uuid.uuid4().hex, self.tenant_id, person.id, self.root_id))
        elif role == "department_admin" and dept_id:
            self.repo.add_admin_scope(__import__("org_core").AdminScope(
                uuid.uuid4().hex, self.tenant_id, person.id, node_id))

        ident = CallerIdentity(user_id, self.tenant_id, person.id, grant.id, role, dept_id)
        self._map[user_id] = ident
        return ident

    def resolve_grant(self, token: Optional[str]) -> Optional[CallerIdentity]:
        """token → org_core 身份。新端点用。无效返回 None。"""
        user = self.auth.resolve(token)
        if user is None:
            return None
        return self.ensure(user.id, getattr(user.role, "value", str(user.role)),
                           getattr(user, "dept_id", None))

    def caller_dict(self, token: Optional[str]) -> Optional[dict]:
        """给 kb_core/txn_agent 等用的 caller 形态(含 grant)。"""
        i = self.resolve_grant(token)
        if not i:
            return None
        return {"id": i.user_id, "tenant_id": i.tenant_id, "grant_id": i.grant_id,
                "person_id": i.person_id, "role": i.role, "dept_id": i.dept_id}

    def provision_person(self, user_id: str, display: str = "") -> str:
        """get-or-create org_core 真人(不建默认grant,供导入器显式派岗)。"""
        if user_id in self._map:
            return self._map[user_id].person_id
        if not hasattr(self, "_persons"):
            self._persons = {}
        if user_id in self._persons:
            return self._persons[user_id]
        import uuid as _uuid
        from org_core import User as _OU, UserKind as _UK, UserStatus as _US
        p = _OU(_uuid.uuid4().hex, self.tenant_id, _UK.INTERNAL, _US.ACTIVE, display or user_id)
        self.repo.add_user(p)
        self._persons[user_id] = p.id
        return p.id
