"""
org_core.permissions — 权限位(perm_key)定义 + 预置岗位模板。

岗位 = 权限位的组合,企业可自定义,也可用 Excel 批量导入(见 role_import)。
这里给出权限位常量(代码里唯一真源)与一批默认模板,方便开箱即用。
"""
from __future__ import annotations

# ----------------------------------------------------------------------------- #
# 权限位(action 维度)。命名:<域>.<动作>
# ----------------------------------------------------------------------------- #
class P:
    # 组织/人员/岗位管理(管理权限:沿管理子树生效)
    ORG_MANAGE = "org.manage"            # 建/改名/合并/拆分组织节点
    USER_MANAGE = "user.manage"          # 建/停用/调动人员
    GRANT_MANAGE = "grant.manage"        # 派岗/建子账号
    ROLE_MANAGE = "role.manage"          # 建岗位/配权限位/Excel 导入

    # 知识库(业务权限:不向下继承,按 grant.org_node 生效)
    KB_READ = "kb.read"
    KB_WRITE_PRIVATE = "kb.write_private"
    KB_PROMOTE = "kb.promote"            # ★ can_promote_kb:把数据晋升进公有高置信(专家/总工)

    # 智能体
    AGENT_CREATE_PRIVATE = "agent.create_private"
    AGENT_PUBLISH = "agent.publish"      # 创建多人可见(部门/公共),须审批
    AGENT_APPROVE = "agent.approve"      # 审批上线

    # 渠道 bot
    BOT_PUBLISH = "bot.publish"          # 受治理发布到飞书/微信

    # 审计(全局可见,独立授予)
    AUDIT_READ = "audit.read"


# 全部权限位(校验导入时用)
ALL_PERMS: frozenset[str] = frozenset(
    v for k, v in vars(P).items() if not k.startswith("_") and isinstance(v, str)
)

MANAGEMENT_PERMS: frozenset[str] = frozenset(
    {P.ORG_MANAGE, P.USER_MANAGE, P.GRANT_MANAGE, P.ROLE_MANAGE}
)  # 这些沿管理子树生效;其余为业务权限,按 grant.org_node 生效


# ----------------------------------------------------------------------------- #
# 预置岗位模板(企业可改、可删、可自建)。key=模板名,value=权限位集合
# ----------------------------------------------------------------------------- #
DEFAULT_ROLE_TEMPLATES: dict[str, frozenset[str]] = {
    "平台管理员": ALL_PERMS,  # 注意:管辖范围仍受 admin_scope 限制,不是无边界
    "组织管理员": frozenset({P.ORG_MANAGE, P.USER_MANAGE, P.GRANT_MANAGE, P.ROLE_MANAGE,
                          P.KB_READ, P.AGENT_APPROVE}),
    "专家/总工": frozenset({P.KB_READ, P.KB_WRITE_PRIVATE, P.KB_PROMOTE,
                         P.AGENT_CREATE_PRIVATE, P.AGENT_PUBLISH, P.BOT_PUBLISH}),
    "开发者": frozenset({P.KB_READ, P.KB_WRITE_PRIVATE, P.AGENT_CREATE_PRIVATE, P.AGENT_PUBLISH}),
    "成员": frozenset({P.KB_READ, P.KB_WRITE_PRIVATE, P.AGENT_CREATE_PRIVATE}),
    "审计员": frozenset({P.AUDIT_READ}),
    "外部协作": frozenset({P.KB_READ}),  # 外来人员默认极小
}


def validate_perm_keys(keys: frozenset[str]) -> frozenset[str]:
    """导入岗位时校验权限位合法,未知位直接报错(显式失败)。"""
    unknown = keys - ALL_PERMS
    if unknown:
        raise ValueError(f"未知权限位: {sorted(unknown)}")
    return keys
