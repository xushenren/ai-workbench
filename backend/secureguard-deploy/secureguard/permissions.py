"""secureguard.permissions — RBAC 权限引擎（Q1 终稿）。

锁定的角色边界：
  - admin            全局：审批智能体上线、管理全部、管理任意配额。
  - department_admin 部门：管本部门知识库与本部门用户配额；**看不到成员私人库原文**。
  - developer        可建智能体；建**私有**不需审批；要**多人可见(部门/公共)**须 admin 审批上线。
  - user             可建**私人智能体**(visibility=private，仅自己、不进市场、不需审批)。

智能体发布状态机（仅当目标可见性为 多人 时才需要）：
    draft → pending_review → published        （admin 审批通过）
              ↘ rejected → draft               （打回）
  私有智能体直接 published（owner-only），不进此状态机。

本引擎是 R-13(跨租户)/R-17(批量导出)/R-18(改删他人) 的执行落点：检查函数返回
(allowed, reason)，状态迁移在越权时抛 PermissionDenied（让误用显式失败）。纯标准库。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class Role(str, Enum):
    ADMIN = "admin"
    RESTRICTED_ADMIN = "restricted_admin"  # 受限管理员：admin 子集，不能碰 admin/造 admin/任命审计员/看私有
    DEPARTMENT_ADMIN = "department_admin"
    DEVELOPER = "developer"
    USER = "user"
    AUDITOR = "auditor"  # 受控审计员：仅有"审计读取"特权，不能管系统/改配置


class Visibility(str, Enum):
    PRIVATE = "private"
    DEPARTMENT = "department"
    PUBLIC = "public"


class AgentStatus(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    REJECTED = "rejected"


class PermissionDenied(Exception):
    """越权操作。携带原因，便于审计与前端提示。"""


@dataclass
class User:
    id: str
    role: Role
    dept_id: Optional[str] = None


@dataclass
class Agent:
    id: str
    owner_id: str
    visibility: Visibility
    status: AgentStatus
    dept_id: Optional[str] = None


@dataclass
class KnowledgeBase:
    id: str
    visibility: Visibility          # public / department / private
    owner_id: Optional[str] = None
    dept_id: Optional[str] = None


Decision = Tuple[bool, str]
MULTI_USER = {Visibility.DEPARTMENT, Visibility.PUBLIC}


# ====================================================================== #
# 智能体：创建 / 发布状态机
# ====================================================================== #
def can_create_agent(user: User, visibility: Visibility) -> Decision:
    """谁能创建何种可见性的智能体。"""
    if visibility == Visibility.PRIVATE:
        return True, "私有智能体：任何角色可建，仅自己可见，不需审批"
    # 多人可见的智能体：普通 user 不能创建
    if user.role == Role.USER:
        return False, "普通用户只能创建私有智能体"
    return True, f"{user.role.value} 可创建 {visibility.value} 智能体（须审批上线）"


def create_agent(user: User, agent_id: str, visibility: Visibility,
                 dept_id: Optional[str] = None) -> Agent:
    """创建智能体。私有直接 published；多人可见进 draft 等审批。"""
    ok, reason = can_create_agent(user, visibility)
    if not ok:
        raise PermissionDenied(reason)
    if visibility == Visibility.PRIVATE:
        return Agent(agent_id, user.id, visibility, AgentStatus.PUBLISHED, dept_id or user.dept_id)
    # 部门可见的智能体，dept_id 默认归创建者部门
    if visibility == Visibility.DEPARTMENT:
        dept_id = dept_id or user.dept_id
    return Agent(agent_id, user.id, visibility, AgentStatus.DRAFT, dept_id)


def submit_for_review(user: User, agent: Agent) -> Agent:
    """提交审核：仅 owner，且必须是多人可见的 draft/rejected。"""
    if agent.visibility == Visibility.PRIVATE:
        raise PermissionDenied("私有智能体无需审核")
    if user.id != agent.owner_id:
        raise PermissionDenied("仅创建者可提交审核")
    if agent.status not in (AgentStatus.DRAFT, AgentStatus.REJECTED):
        raise PermissionDenied(f"状态 {agent.status.value} 不可提交")
    agent.status = AgentStatus.PENDING_REVIEW
    return agent


def can_approve(user: User, agent: Agent) -> Decision:
    """审批权：admin 可批所有多人可见智能体。

    默认遵循 Q1 终稿"多人可见须 admin 审批"。如需把【部门可见】的审批权下放给
    对应 department_admin，把下面的开关打开即可（默认关，以严格对齐你的决策）。
    """
    DELEGATE_DEPT_APPROVAL_TO_DEPT_ADMIN = False
    if user.role in _ADMIN_TIER:
        return True, "管理员审批"
    if (DELEGATE_DEPT_APPROVAL_TO_DEPT_ADMIN
            and user.role == Role.DEPARTMENT_ADMIN
            and agent.visibility == Visibility.DEPARTMENT
            and user.dept_id == agent.dept_id):
        return True, "部门管理员审批本部门智能体"
    return False, "仅 admin 可审批智能体上线"


def approve(user: User, agent: Agent) -> Agent:
    ok, reason = can_approve(user, agent)
    if not ok:
        raise PermissionDenied(reason)
    if agent.status != AgentStatus.PENDING_REVIEW:
        raise PermissionDenied(f"状态 {agent.status.value} 不可审批")
    agent.status = AgentStatus.PUBLISHED
    return agent


def reject(user: User, agent: Agent) -> Agent:
    ok, reason = can_approve(user, agent)
    if not ok:
        raise PermissionDenied(reason)
    agent.status = AgentStatus.REJECTED
    return agent


def can_use_agent(user: User, agent: Agent) -> Decision:
    """谁能在聊天里使用/看到某智能体。未发布的多人智能体仅创建者(+审批人)可见。"""
    if agent.status in (AgentStatus.DRAFT, AgentStatus.PENDING_REVIEW, AgentStatus.REJECTED):
        if user.id == agent.owner_id:
            return True, "创建者可见自己未发布的智能体"
        if agent.status == AgentStatus.PENDING_REVIEW and can_approve(user, agent)[0]:
            return True, "审批人可预览待审智能体"
        return False, "未发布，仅创建者/审批人可见"
    # 已发布
    if agent.visibility == Visibility.PRIVATE:
        return (user.id == agent.owner_id), "私有智能体仅创建者"
    if agent.visibility == Visibility.DEPARTMENT:
        return (user.dept_id == agent.dept_id), "部门智能体限本部门"
    return True, "公共智能体全员可用"


# ====================================================================== #
# 知识库隔离（D7）：访问 / 读原文 / 管理
# ====================================================================== #
def can_access_kb(user: User, kb: KnowledgeBase) -> Decision:
    """检索可达性：公共 + 本部门 + 自己私有。绝不可达他人私有。"""
    if kb.visibility == Visibility.PUBLIC:
        return True, "公共库全员可检索"
    if kb.visibility == Visibility.DEPARTMENT:
        return (user.dept_id == kb.dept_id), "部门库限本部门"
    return (user.id == kb.owner_id), "私有库仅本人"


def can_read_kb_content(user: User, kb: KnowledgeBase) -> Decision:
    """读取原文。私有库**仅 owner**——admin/部门管理员都不能看原文（D7）。

    与 can_access_kb 的区别：管理员为合规可"管理"私有库（见 can_manage_kb），
    但**读原文**这条线对私有库只认 owner，连 admin 也不行。
    """
    if kb.visibility == Visibility.PRIVATE:
        return (user.id == kb.owner_id), "私有库原文仅本人可读，admin 亦不可"
    return can_access_kb(user, kb)


def can_manage_kb(user: User, kb: KnowledgeBase) -> Decision:
    """生命周期管理（删除/隔离/合规处置），不含读原文。"""
    if user.role in _ADMIN_TIER:
        return True, "管理员可管理任意库（但私有库不可读原文）"
    if user.role == Role.DEPARTMENT_ADMIN and kb.visibility == Visibility.DEPARTMENT \
            and user.dept_id == kb.dept_id:
        return True, "部门管理员管理本部门库"
    if kb.visibility == Visibility.PRIVATE and user.id == kb.owner_id:
        return True, "owner 管理自己私有库"
    return False, "无管理权"


def can_audit_read_kb(user: User, kb: KnowledgeBase) -> Decision:
    """**受控审计读取**：仅 auditor 角色可读取任意库原文（含他人私有库）。

    与 can_read_kb_content 严格分离——日常路径下私有库仍仅 owner 可读，admin 也不行。
    本特权的"受控"体现在端点层：必须带 reason，且每次访问写入哈希链审计（可问责、不可篡改）。
    admin 没有此权（职责分离：管系统的≠能看私有内容的）。
    """
    if user.role == Role.AUDITOR:
        return True, "审计员受控读取（须留痕）"
    return False, "无审计读取权（仅 auditor 角色）"


_ADMIN_TIER = {Role.ADMIN, Role.RESTRICTED_ADMIN}
_PRIVILEGED = {Role.ADMIN, Role.RESTRICTED_ADMIN, Role.AUDITOR}  # 只有 admin 能授予/撤销这些


def can_manage_users(actor: User) -> Decision:
    """列出/分配部门/审批部门申请：admin 或受限管理员。"""
    if actor.role in _ADMIN_TIER:
        return True, "管理员可管理用户"
    return False, "仅管理员可管理用户"


def can_manage_admins(actor: User) -> Decision:
    """授予/撤销受限管理员、删除受限管理员、任命审计员：**仅 admin**。"""
    if actor.role == Role.ADMIN:
        return True, "仅 admin 可管理管理员/审计员任命"
    return False, "仅 admin 可授予/撤销受限管理员与审计员"


def can_set_role(actor: User, target: User, new_role: Role) -> Decision:
    """改某人角色的护栏（防自我提权 / 防受限管理员造 admin / 防绕过审计员任命）。"""
    if actor.role not in _ADMIN_TIER:
        return False, "无用户管理权"
    # 谁都不能改 admin 的角色，除了 admin 自己这一层里——受限管理员绝不能碰 admin
    if target.role == Role.ADMIN and actor.role != Role.ADMIN:
        return False, "受限管理员不能修改 admin"
    # 授予特权角色(admin/受限管理员/审计员)只能由 admin 来
    if new_role in _PRIVILEGED and actor.role != Role.ADMIN:
        return False, f"仅 admin 可授予 {new_role.value}（防自我提权/绕过审计任命）"
    return True, "可改角色"


def can_delete_user(actor: User, target: User) -> Decision:
    """删除用户的护栏。受限管理员不能删 admin/受限管理员/审计员（防移除监督）。"""
    if actor.role not in _ADMIN_TIER:
        return False, "无用户管理权"
    if actor.role == Role.ADMIN:
        return (target.role != Role.ADMIN), ("不能删除 admin" if target.role == Role.ADMIN else "admin 可删除非 admin")
    # 受限管理员：只能删普通层级，碰不得特权角色
    if target.role in _PRIVILEGED:
        return False, "受限管理员不能删除 admin/受限管理员/审计员"
    return True, "受限管理员可删除普通用户"


# ====================================================================== #
# 配额管理
# ====================================================================== #
def can_manage_quota(actor: User, target: User) -> Decision:
    """谁能调整某用户的配额。admin/受限管理员 全局；部门管理员限本部门；user 无。"""
    if actor.role in _ADMIN_TIER:
        return True, "管理员管理全局配额"
    if actor.role == Role.DEPARTMENT_ADMIN and actor.dept_id == target.dept_id:
        return True, "部门管理员管理本部门用户配额"
    return False, "无配额管理权"
