"""
org_core.models — 组织/权限/多租户 的领域模型(定稿)。

七个实体:tenant / org_node / user / role(岗位) / grant(子账号=人+岗位+组织节点) /
admin_scope(管理子树) / audit。纯 stdlib dataclass,与存储实现解耦。

设计要点(对齐已定决策):
  - grant 即"子账号/任职":一个真人(user)可有多条 grant,各挂不同岗位与组织节点,可切换。
  - 业务权限不向下继承:scope = grant.org_node_id 本身。
  - 管理权限沿子树向下:admin_scope 给定一个可管理的子树根。
  - 一切带 tenant_id:组织树即租户边界。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NodeType(str, Enum):
    COMPANY = "company"        # 公司/子公司
    DEPARTMENT = "department"  # 部门
    PROJECT = "project"        # 项目部
    TEAM = "team"              # 班组


class UserKind(str, Enum):
    INTERNAL = "internal"      # 企业自有人员
    EXTERNAL = "external"      # 外来人员(默认零权限,只能被显式授予)


class UserStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"      # 离职关停:一刀停其所有 grant


class Visibility(str, Enum):   # 沿用既有语义
    PRIVATE = "private"
    DEPARTMENT = "department"
    PUBLIC = "public"


class PermissionDenied(Exception):
    """越权操作。携带原因,便于审计与前端提示。"""


@dataclass
class Tenant:
    id: str
    name: str


@dataclass
class OrgNode:
    id: str
    tenant_id: str
    parent_id: Optional[str]    # None = 租户根
    type: NodeType
    name: str                   # 可改名


@dataclass
class User:
    id: str
    tenant_id: str
    kind: UserKind = UserKind.INTERNAL
    status: UserStatus = UserStatus.ACTIVE
    display_name: str = ""


@dataclass
class Role:
    """岗位 = 一组权限位的打包(企业自定义,可 Excel 批量导入)。"""
    id: str
    tenant_id: str
    name: str
    perm_keys: frozenset[str] = field(default_factory=frozenset)


@dataclass
class Grant:
    """子账号/任职 = 人 + 岗位 + 组织节点(scope)。一个 user 可有多条。"""
    id: str
    tenant_id: str
    user_id: str
    role_id: str
    org_node_id: str            # 业务权限作用域(不向下继承)
    label: str = ""             # 任职名,如 "张三@B项目部-顾问"
    active: bool = True
    is_default: bool = False    # 默认登录身份


@dataclass
class AdminScope:
    """管理员的管理子树:可在该节点及其后代内建人/派岗/调组织。"""
    id: str
    tenant_id: str
    user_id: str
    org_node_id: str            # 可管理的子树根


@dataclass
class AuditEntry:
    id: str
    tenant_id: str
    user_id: str                # 真人
    grant_id: Optional[str]     # 以哪个子账号操作
    action: str
    target: str
    ok: bool
    reason: str
    ts: float = field(default_factory=time.time)
    prev_hash: str = ""
    hash: str = ""
