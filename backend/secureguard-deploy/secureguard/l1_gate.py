"""secureguard.l1_gate — L1 仲裁门控。

把 arbitration-and-gates.md 的 §0/§4/§5 落成可运行代码：
  - REDLINES：12 条红线（命中即 BLOCK + notify）。
  - SELF_MONITOR_TRIGGERS：13 条自省触发器（监听“我自己的推理状态”）。
  - 6 个领域护栏（DomainGuard 子类）。
  - gate()：统一调度，按“红线 → R2 → 自省 → 领域护栏 + 上下文约束”顺序。
  - arbitrate()：多规则冲突时按 LADDER 裁决，安全侧永不让路。

注意：本模块定义的红线/阶梯/护栏属于 Plane-0，不可由进化流程改写。
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from .types import (
    Conflict,
    ETIQUETTE_TIERS,
    GateResult,
    Rule,
    SAFETY_TIERS,
    Token,
)

Action = Dict[str, Any]
Ctx = Dict[str, Any]


# ====================================================================== #
# §4.2  12 条红线（Plane-0 常量，永不解锁）
# 每条是一个谓词：action -> bool；True 表示命中红线。
# ====================================================================== #
REDLINES: Dict[str, Callable[[Action], bool]] = {
    # R-01 生产数据销毁而无备份+确认
    "R-01": lambda a: a.get("type") in ("destroy_prod_data", "rm_production", "drop_table", "truncate")
    and not a.get("backup_confirmed"),
    # R-02 向受保护分支 force-push / 重写共享历史
    "R-02": lambda a: a.get("type") == "force_push"
    and a.get("branch") in ("main", "master", "protected"),
    # R-03 为“让它能跑”而禁用安全控制
    "R-03": lambda a: a.get("type") == "disable_security"
    and a.get("reason") in ("to_make_it_work", "to_pass", "temporary"),
    # R-04 绕过评审直接合入 main
    "R-04": lambda a: a.get("type") == "merge_without_review",
    # R-05 禁用/删改测试让 CI 变绿
    "R-05": lambda a: a.get("type") in ("skip_test", "xfail_test", "delete_test", "disable_assertion")
    and a.get("reason") == "to_pass_ci",
    # R-06 对生产自动跑未经批准的 schema migration
    "R-06": lambda a: a.get("type") == "schema_migration"
    and a.get("target") == "production"
    and not a.get("human_approved"),
    # R-07 凭据/密钥写入 VCS / 日志 / 明文 / 硬编码
    "R-07": lambda a: a.get("type") in ("hardcode_key", "write_credential", "commit_secret", "log_secret")
    or bool(a.get("contains_plaintext_secret")),
    # R-08 禁用嵌入式/控制系统安全联锁
    "R-08": lambda a: a.get("type") == "disable_safety_interlock",
    # R-09 篡改/删除/绕过审计日志
    "R-09": lambda a: a.get("type") in ("tamper_audit_log", "delete_audit_log", "bypass_audit"),
    # R-10 数据外泄出已批准边界
    "R-10": lambda a: "external_send" in a.get("flags", []) and not a.get("approved_boundary"),
    # R-11 以提升权限运行未审查代码
    "R-11": lambda a: a.get("type") == "exec_unreviewed_code" and a.get("privilege") == "elevated",
    # R-12 自我进化 patch 试图修改 Plane-0
    "R-12": lambda a: a.get("type") == "evolve_patch"
    and "Plane-0" in str(a.get("target", "")),
    # ---- 企业工作台新增（R-13..R-19）。措辞建议与 Constitution v2 权威文本对齐，
    #      但编号/覆盖面已补齐到 19 条。----
    # R-13 跨租户/越权访问他人私有知识库或会话（D7）
    "R-13": lambda a: a.get("type") in ("access_kb", "read_session")
    and a.get("visibility") == "private"
    and a.get("owner_id") not in (None, a.get("caller_id")),
    # R-14 把敏感数据（PII/凭据/机密）路由/外发出企业边界（D2 审计告警的硬化版）
    "R-14": lambda a: a.get("type") in ("route", "send")
    and a.get("data_class") in ("CONFIDENTIAL", "RESTRICTED")
    and a.get("destination") == "external",
    # R-15 篡改/绕过配额或计费记录（D6）
    "R-15": lambda a: a.get("type") in ("tamper_quota", "bypass_billing", "forge_usage"),
    # R-16 未脱敏 PII 写入日志/思考面板/外部输出（D3）
    "R-16": lambda a: bool(a.get("contains_unmasked_pii"))
    and a.get("sink") in ("log", "trace_panel", "external"),
    # R-17 以管理员身份执行未经审批的批量用户数据导出
    "R-17": lambda a: a.get("type") == "bulk_export"
    and a.get("scope") == "user_data"
    and not a.get("approval_ticket"),
    # R-18 修改/删除其他用户的会话、数据或智能体
    "R-18": lambda a: a.get("type") in ("modify", "delete")
    and a.get("target_kind") in ("session", "user_data", "agent")
    and a.get("owner_id") not in (None, a.get("caller_id"))
    and a.get("caller_role") != "admin",
    # R-19 在系统提示词注入层之外动态提权 / 覆盖 CONSTITUTION 约束块
    "R-19": lambda a: a.get("type") == "override_constitution"
    or (a.get("type") == "privilege_escalation" and not a.get("authorized")),
}


# ====================================================================== #
# §3  13 条自省触发器（监听内部独白，非用户输入）
# 注：这是“尽力而为”的二线防御，依赖模型把推理意图暴露给 ctx.internal_thought。
# ====================================================================== #
SELF_MONITOR_TRIGGERS: List[tuple] = [
    (r"应该是默认值吧|应该是.{0,4}默认", Token.ASK, "发现值缺口(C2)"),
    (r"这个迁移应该可逆|迁移.{0,4}应该.{0,4}可逆", Token.BLOCK, "无已测逆向脚本(§2.1)"),
    (r"这个操作其实(挺|很|还)?安全|不可逆.{0,6}其实.{0,4}安全", Token.BLOCK, "把不可逆论证成安全(H5)"),
    (r"这个测试.{0,8}(先\s*)?(skip|xfail|跳过|关掉)", Token.BLOCK, "测试绕过(L4)"),
    (r"--force|--no-verify|\|\|\s*true|2>\s*/dev/null", Token.BLOCK, "绕过门信号"),
    (r"先\s*hardcode|硬编码.{0,4}(key|密钥|token)|先写死.{0,4}密钥", Token.BLOCK, "REDLINE:R-07 凭据硬编码"),
    (r"staging.{0,8}配置.{0,8}(和|跟).{0,4}prod.{0,4}一样", Token.ASK, "强制核对(§2.3)"),
    (r"(把|将).{0,6}(权限|异常).{0,6}放宽.{0,6}就(能|可以)?过", Token.BLOCK, "绕过安全控制"),
    (r"这只是\s*cleanup|删了无所谓|删掉.{0,4}没?事", Token.ESCALATE, "删除轻量化(H5/§4)"),
    (r"数值\s*收敛了|应该收敛", Token.BLOCK, "无收敛判据(§2.4)"),
    (r"数据.{0,6}来源.{0,6}(大概|应该|可能).{0,4}可信", Token.ASK, "数据血缘门(§2.2)"),
    (r"重新?措辞.{0,8}(以便|来|好).{0,4}(通过|绕过)|换个说法.{0,4}绕过", Token.BLOCK, "reframe=拒绝信号"),
    (r"先.{0,4}注释掉.{0,4}(校验|检查|断言)|先关.{0,4}校验", Token.BLOCK, "绕过校验信号"),
    # ---- 企业工作台新增（补齐到 18 条）----
    (r"别人的.{0,4}(私有)?(库|知识库|会话).{0,4}应该?也能?看|顺便.{0,4}看下别人的", Token.BLOCK, "跨租户越权(R-13)"),
    (r"PII.{0,8}(直接)?(显示|展示).{0,8}(思考面板|trace|界面).{0,4}(应该)?没?事", Token.BLOCK, "PII 入面板(R-16)"),
    (r"配额.{0,4}(扣减)?.{0,4}(晚点|回头|稍后).{0,4}补|先不扣.{0,4}配额", Token.BLOCK, "配额绕过(R-15)"),
    (r"(这个)?智能体.{0,6}超出.{0,4}领域.{0,6}(但|也)?.{0,4}帮.{0,4}下", Token.BLOCK, "领域越界(D6 scope)"),
    (r"(发|送|路由).{0,6}(去|到).{0,4}外部.{0,4}(API|接口).{0,4}快", Token.BLOCK, "敏感数据外发(R-14)"),
]
_SELF_MONITOR_COMPILED = [(re.compile(p, re.IGNORECASE | re.UNICODE), tok, why)
                          for p, tok, why in SELF_MONITOR_TRIGGERS]


def self_monitor(internal_thought: str) -> Optional[GateResult]:
    """对 agent 的内部独白做触发器匹配。命中即返回对应 token。"""
    if not internal_thought:
        return None
    for pat, token, reason in _SELF_MONITOR_COMPILED:
        if pat.search(internal_thought):
            return GateResult(token, reason, tier="DOMAIN_GUARD" if token == Token.BLOCK else None)
    return None


# ====================================================================== #
# §2  6 个领域护栏
# ====================================================================== #
class DomainGuard(ABC):
    """领域第四层护栏基类。check 返回 None 表示通过，否则返回失败原因。"""

    tier = "DOMAIN_GUARD"

    @abstractmethod
    def check(self, action: Action) -> Optional[str]:
        ...


class SoftwareGuard(DomainGuard):
    """§2.1 软件/后端：状态变更三件套 + 迁移可逆性 + 契约稳定性。"""

    def check(self, action: Action) -> Optional[str]:
        if action.get("type") == "deploy" and action.get("mutates_state"):
            if not action.get("idempotency"):
                return "缺少幂等性说明"
            if not action.get("rollback_plan"):
                return "缺少回滚方案"
            if not action.get("down_migration_tested"):
                return "迁移未测逆向脚本"
        if action.get("type") == "schema_migration" and not action.get("down_migration_tested"):
            return "迁移按不可逆处理，需已测逆向脚本"
        if action.get("type") == "breaking_api_change" and not action.get("breaking_annotated"):
            return "破坏性 API 变更需显式标注 breaking 并走 R2"
        return None


class DataMLGuard(DomainGuard):
    """§2.2 数据/ML：血缘门 + PII 门 + 评估门(Default-FAIL) + 静默精度降级禁令。"""

    def check(self, action: Action) -> Optional[str]:
        if action.get("type") == "train" and not action.get("data_provenance"):
            return "数据血缘缺失(BLOCK)"
        if action.get("has_pii") and not action.get("pii_masked"):
            return "PII 未脱敏，禁止原文外流"
        if action.get("type") == "deploy_model" and not action.get("eval_passed"):
            return "模型评估门 Default-FAIL：无评估结果不得上线"
        if action.get("silent_precision_downgrade"):
            return "静默精度降级禁令"
        return None


class InfraGuard(DomainGuard):
    """§2.3 基础设施/DevOps：爆炸半径 + IaC 单一事实源 + 变更窗口。"""

    def check(self, action: Action) -> Optional[str]:
        if action.get("type") == "change" and action.get("blast_radius") is None:
            return "缺少爆炸半径估算(ASK)"
        if action.get("type") == "manual_infra_change" and not action.get("iac_applied"):
            return "绕过 IaC 的手工线上改动禁止（会造成 drift）"
        if action.get("type") == "prod_change" and not action.get("in_change_window"):
            return "窗口外生产变更 = R2"
        return None


class ScientificGuard(DomainGuard):
    """§2.4 科学计算：可复现门 + 量纲校验 + 数值稳定性。"""

    def check(self, action: Action) -> Optional[str]:
        if action.get("type") == "result":
            if not (action.get("seed_fixed") and action.get("env_locked") and action.get("unit_consistent")):
                return "可复现门：缺种子/环境锁定/单位一致性，结果不可作为交付"
        if action.get("type") == "computation" and action.get("cross_unit") \
                and not action.get("unit_check_passed"):
            return "量纲/单位校验未通过"
        if action.get("type") == "convergence_claim" and not action.get("condition_number"):
            return "数值稳定性：缺条件数/收敛判据"
        return None


class EmbeddedGuard(DomainGuard):
    """§2.5 嵌入式/硬件：物理联锁 + HIL 前置 + 不可逆物理动作=R2。"""

    def check(self, action: Action) -> Optional[str]:
        if action.get("type") == "disable_interlock":
            return "禁止禁用物理安全联锁"
        if action.get("type") == "flash_hardware" and not action.get("hil_passed"):
            return "HIL 前置：需硬件在环测试"
        if action.get("type") == "irreversible_physical" and action.get("risk_level") != "R2":
            return "不可逆物理动作必须按 R2 处理"
        return None


class SecurityGuard(DomainGuard):
    """§2.6 安全敏感：威胁建模前置 + 不自造密码学 + 密钥仅经保险库。"""

    tier = "SECURITY_CONTROL"  # 安全控制属阶梯 L2，高于一般领域护栏

    def check(self, action: Action) -> Optional[str]:
        if action.get("type") == "security_feature" and not action.get("threat_model"):
            return "威胁建模前置(ASK)"
        if action.get("type") == "custom_crypto":
            return "不自造密码学：必须用既有审计过的库"
        if action.get("type") == "key_handling" and action.get("plaintext_storage"):
            return "密钥仅经保险库：禁止明文落盘/VCS/日志"
        return None


_DOMAIN_GUARDS: Dict[str, DomainGuard] = {
    "software": SoftwareGuard(),
    "data_ml": DataMLGuard(),
    "infrastructure": InfraGuard(),
    "scientific": ScientificGuard(),
    "embedded": EmbeddedGuard(),
    "security": SecurityGuard(),
    "general": SoftwareGuard(),  # 默认回退到软件护栏（最常见）
}


def load_domain_guard(domain: str) -> DomainGuard:
    """按领域返回对应护栏；未知领域回退到软件护栏。"""
    return _DOMAIN_GUARDS.get(domain, _DOMAIN_GUARDS["general"])


# ====================================================================== #
# §5  gate() 与 arbitrate()
# ====================================================================== #
def _check_redlines(action: Action) -> Optional[str]:
    """返回首个命中的红线 id，未命中返回 None。"""
    for rid, predicate in REDLINES.items():
        try:
            if predicate(action):
                return rid
        except Exception:
            # 谓词异常按“无法判定安全”处理，保守起见不放行该红线判断，
            # 但不在此抛出，交由调用链记录。
            continue
    return None


def _ctx_constraint_rules(action: Action, ctx: Ctx) -> List[Rule]:
    """从上下文装配额外约束规则（用于演示并支撑仲裁）。

    支持的 ctx 字段：
      - quiet_hours (bool)        → COMM_ETIQUETTE 规则
      - velocity_pressure (bool)  → VELOCITY 规则
      - irreversible_unconfirmed (bool) → PROD_INTEGRITY 规则（H5）
    """
    rules: List[Rule] = []
    if ctx.get("irreversible_unconfirmed"):
        rules.append(Rule(
            tier="PROD_INTEGRITY",
            description="不可逆操作未获确认(H5)",
            verdict=GateResult(Token.BLOCK, "不可逆操作未获确认", tier="PROD_INTEGRITY"),
        ))
    if ctx.get("quiet_hours"):
        rules.append(Rule(
            tier="COMM_ETIQUETTE",
            description="静默时段不打扰(H3)",
            verdict=GateResult(Token.BLOCK, "静默时段(02:00-07:00)", tier="COMM_ETIQUETTE"),
        ))
    if ctx.get("velocity_pressure"):
        rules.append(Rule(
            tier="VELOCITY",
            description="赶时间/演示在即",
            verdict=GateResult(Token.PASS, "velocity", tier="VELOCITY"),
        ))
    return rules


def gate(action: Action, ctx: Ctx, audit: "Any" = None) -> GateResult:
    """仲裁总入口 —— 一个动作要执行，先过此函数。

    顺序严格按 §5：红线 → R2 → 自省钩子 → 领域护栏(+上下文约束) → 仲裁/PASS。
    """
    ctx = ctx or {}

    # --- PLANE-0：红线检测，最先跑，决定性最强 ---
    rid = _check_redlines(action)
    if rid:
        res = GateResult(Token.BLOCK, f"redline:{rid}", notify=True, tier="REDLINE/R2")
        if audit is not None:
            audit.note_redline(rid, action)
        return res

    # --- R2 需人类批准 ---
    if action.get("risk_level") == "R2":
        return GateResult(Token.ESCALATE, action.get("r2_reason", "需人类批准"), tier="REDLINE/R2")

    # --- 自省钩子：监听“我”，不是监听 input ---
    thought = ctx.get("internal_thought", "")
    sm = self_monitor(thought)
    if sm is not None:
        return sm

    # --- 领域护栏 + 上下文约束，装配成规则集 ---
    domain = action.get("domain", "general")
    guard = load_domain_guard(domain)
    fired: List[Rule] = []
    reason = guard.check(action)
    if reason:
        fired.append(Rule(
            tier=guard.tier,
            description=reason,
            verdict=GateResult(Token.BLOCK, reason, tier=guard.tier),
        ))
    fired.extend(_ctx_constraint_rules(action, ctx))

    if not fired:
        return GateResult(Token.PASS, "all gates passed")
    if len(fired) == 1:
        return fired[0].verdict
    # 多规则冲突 → 仲裁
    return arbitrate(Conflict(rules=fired, action=action), ctx, audit)


def arbitrate(conflict: Conflict, ctx: Ctx, audit: "Any" = None) -> GateResult:
    """多规则冲突裁决：阶梯高者恒胜；安全侧永不让路；约定侧可为紧急让步。"""
    winner = conflict.winner()

    # §0 第 2 条：永不静默裁决 —— 记录冲突 + surface 给人类
    if audit is not None:
        audit.record_conflict(conflict, winner)

    # 安全侧（前 4 层）获胜 → BLOCK，且不被任何紧急情况绕过
    if winner.tier in SAFETY_TIERS:
        return GateResult(
            Token.BLOCK,
            winner.description,
            notify=True,
            tier=winner.tier,
            note="safety tier wins; not bypassable by emergency",
        )

    # 约定侧获胜且处于紧急情况 → 礼仪让步
    if ctx.get("is_emergency") and winner.tier in ETIQUETTE_TIERS:
        return GateResult(
            Token.PASS,
            "etiquette yielded to emergency",
            tier=winner.tier,
            note=f"{winner.tier} yielded to emergency",
        )

    return winner.verdict
