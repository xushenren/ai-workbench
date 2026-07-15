"""backend.permission_matrix — 集中权限矩阵（单一事实源）。

把"哪个角色能做哪件事"集中定义在一处：
  - 后端各端点用 can(role, capability) 校验
  - 权限说明书页面从同一份 MATRIX 自动生成（说明书 = 实际权限，永不脱节）

简化版：全部按角色直接判（不引入授权表/组织架构）。带"限本部门"等条件的，
端点内再做范围判断（如 dept_admin 只能管本部门）。
"""
from __future__ import annotations

from typing import Dict, List
from secureguard.permissions import Role

# 能力清单（capability）：每条 = 一个可授予的动作
CAP_MANAGE_ADMINS = "manage_admins"           # 动其他管理员 / 提升为 admin
CAP_MANAGE_USERS = "manage_users"             # 新建/编辑/冻结/删用户
CAP_SET_USER_ROLE = "set_user_role"           # 改用户角色（非管理员）
CAP_CONFIG_MODEL = "config_model"             # 模型配置（接 API key）
CAP_CREATE_AGENT = "create_agent"             # 建智能体
CAP_CREATE_KB = "create_kb"                   # 建知识库
CAP_CREATE_PRIVATE = "create_private"         # 建私有资产（user 也可）
CAP_SHARE_GLOBAL = "share_global"             # 共享到全局
CAP_ISSUE_SK = "issue_sk"                     # 签发调用密钥
CAP_AUDIT_READ = "audit_read"                 # 审计查看（只读）
CAP_USE_PLATFORM = "use_platform"             # 用智能体/会话/上传/语音

# 每个能力 → 允许的角色集合（这就是你确认的那张矩阵）
MATRIX: Dict[str, set] = {
    CAP_MANAGE_ADMINS:  {Role.ADMIN},
    CAP_MANAGE_USERS:   {Role.ADMIN, Role.RESTRICTED_ADMIN, Role.DEPARTMENT_ADMIN},  # dept_admin 限本部门
    CAP_SET_USER_ROLE:  {Role.ADMIN, Role.RESTRICTED_ADMIN},
    CAP_CONFIG_MODEL:   {Role.ADMIN},
    CAP_CREATE_AGENT:   {Role.ADMIN, Role.DEVELOPER},
    CAP_CREATE_KB:      {Role.ADMIN, Role.DEVELOPER},
    CAP_CREATE_PRIVATE: {Role.ADMIN, Role.DEVELOPER, Role.USER, Role.RESTRICTED_ADMIN,
                         Role.DEPARTMENT_ADMIN, Role.AUDITOR},
    CAP_SHARE_GLOBAL:   {Role.ADMIN, Role.DEVELOPER},
    CAP_ISSUE_SK:       {Role.ADMIN},
    CAP_AUDIT_READ:     {Role.ADMIN, Role.AUDITOR},
    CAP_USE_PLATFORM:   {Role.ADMIN, Role.RESTRICTED_ADMIN, Role.DEVELOPER,
                         Role.DEPARTMENT_ADMIN, Role.AUDITOR, Role.USER},
}

# 能力的人类可读说明（用于权限说明书）
CAP_LABELS: Dict[str, str] = {
    CAP_MANAGE_ADMINS:  "管理其他管理员 / 提升为超级管理员",
    CAP_MANAGE_USERS:   "新建、编辑、冻结、删除用户",
    CAP_SET_USER_ROLE:  "修改普通用户的角色",
    CAP_CONFIG_MODEL:   "配置模型（接入 API、填写密钥）",
    CAP_CREATE_AGENT:   "创建智能体",
    CAP_CREATE_KB:      "创建知识库",
    CAP_CREATE_PRIVATE: "创建私有智能体 / 私有知识库",
    CAP_SHARE_GLOBAL:   "将智能体 / 知识库共享到全局",
    CAP_ISSUE_SK:       "签发对外调用密钥（sk）",
    CAP_AUDIT_READ:     "查看审计日志（只读）",
    CAP_USE_PLATFORM:   "使用智能体对话、会话、文件上传、语音",
}

# 条件注脚（矩阵里有范围限制的，说明书额外标注）
CAP_NOTES: Dict[str, str] = {
    CAP_MANAGE_USERS: "部门管理员仅限本部门用户；受限管理员不能操作任何管理员账户。",
    CAP_SET_USER_ROLE: "不能将用户提升为管理员（仅超级管理员可）。",
    CAP_CREATE_AGENT: "普通用户只能创建私有智能体；共享到全局需开发者及以上。",
}

ROLE_LABELS: Dict[str, str] = {
    Role.ADMIN.value: "超级管理员",
    Role.RESTRICTED_ADMIN.value: "受限管理员",
    Role.DEPARTMENT_ADMIN.value: "部门管理员",
    Role.DEVELOPER.value: "开发者",
    Role.USER.value: "普通用户",
    Role.AUDITOR.value: "审计员",
}


def can(role: Role, capability: str) -> bool:
    """该角色是否拥有此能力。"""
    allowed = MATRIX.get(capability, set())
    return role in allowed


def capabilities_of(role: Role) -> List[str]:
    """某角色拥有的全部能力（用于说明书/前端按角色显示）。"""
    return [cap for cap, roles in MATRIX.items() if role in roles]


def build_handbook() -> Dict[str, object]:
    """生成权限说明书数据（管理员可见）。与 MATRIX 同源，永不脱节。"""
    roles = [Role.ADMIN, Role.RESTRICTED_ADMIN, Role.DEPARTMENT_ADMIN,
             Role.DEVELOPER, Role.USER, Role.AUDITOR]
    capabilities = []
    for cap, label in CAP_LABELS.items():
        capabilities.append({
            "id": cap, "label": label,
            "note": CAP_NOTES.get(cap, ""),
            "roles": {r.value: (r in MATRIX.get(cap, set())) for r in roles},
        })
    return {
        "roles": [{"id": r.value, "label": ROLE_LABELS[r.value]} for r in roles],
        "capabilities": capabilities,
    }
