"""secureguard.types — 全栈共享的数据类型。

集中定义五层共用的枚举与数据类，避免循环依赖。所有类型都是纯标准库实现，
不引入任何第三方依赖，保证安全关键层可以离线运行与测试。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Token(str, Enum):
    """门控四态。继承 str 便于 JSON 序列化与日志打印。

    PASS     — 该门通过，放行至下一层。
    ASK      — 信息缺口，需向人类补全后从本门重入。
    BLOCK    — 命中约束，方案不可行，终止该动作。
    ESCALATE — 需人类显式批准（R2 / 红线邻域）。
    """

    PASS = "PASS"
    ASK = "ASK"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"


# 仲裁阶梯（arbitration-and-gates.md §0）。索引越小优先级越高。
# 前 4 层为“安全侧”，永不为任何紧急情况让路。
LADDER: List[str] = [
    "REDLINE/R2",        # L0  红线 / 需人类批准的不可逆操作
    "PROD_INTEGRITY",    # L1  线上数据/状态完整性（H5 不可逆）
    "SECURITY_CONTROL",  # L2  安全控制（认证/加密/密钥/权限/审计）
    "DOMAIN_GUARD",      # L3  领域第四层护栏（H6）
    "CORRECTNESS_GATE",  # L4  测试/评估/可复现门（Default-FAIL）
    "HUMAN_APPROVAL",    # L5  R1 类需确认操作（H1）
    "DELIVERY",          # L6  交付铁律（H4）
    "COMM_ETIQUETTE",    # L7  通信礼仪（H3，含静默时段）
    "FORK",              # L8  异步分流（H2）
    "VELOCITY",          # L9  速度与优化偏好
]

# 安全侧层级集合：被触发时只会让约定侧让路，自己永不让路。
SAFETY_TIERS = set(LADDER[:4])
# 约定侧层级集合：可为紧急情况让步。
ETIQUETTE_TIERS = {"DELIVERY", "COMM_ETIQUETTE", "FORK", "VELOCITY"}


def tier_rank(tier: str) -> int:
    """返回某层级在阶梯上的序号；未知层级排到最低优先级。"""
    try:
        return LADDER.index(tier)
    except ValueError:
        return len(LADDER)  # 未知层级 = 最低优先级


@dataclass
class GateResult:
    """单个门的判定结果。"""

    token: Token
    reason: str = ""
    notify: bool = False          # 是否需要通知人类（红线命中时为 True）
    tier: Optional[str] = None    # 触发该判定的阶梯层级
    note: str = ""                # 仲裁附注（例如“礼仪为紧急让步”）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token": self.token.value,
            "reason": self.reason,
            "notify": self.notify,
            "tier": self.tier,
            "note": self.note,
        }


@dataclass
class Rule:
    """一条被触发的规则。仲裁器据此在阶梯上比较优先级。"""

    tier: str                 # 该规则所属阶梯层级（见 LADDER）
    description: str          # 人类可读的触发原因
    verdict: GateResult       # 该规则单独主张的结果

    def rank(self) -> int:
        return tier_rank(self.tier)


@dataclass
class Conflict:
    """两条及以上规则同时触发时构造，交给 arbitrate() 裁决。"""

    rules: List[Rule]
    action: Dict[str, Any] = field(default_factory=dict)

    def winner(self) -> Rule:
        """阶梯上优先级最高（rank 最小）的规则获胜。"""
        return min(self.rules, key=lambda r: r.rank())


@dataclass
class TrapResult:
    """L0 输入守卫命中的单条陷阱。"""

    hit: bool
    trap_type: str
    evidence: str
    action: str  # BLOCK / SANITIZE / ASK
    pattern_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hit": self.hit,
            "trap_type": self.trap_type,
            "evidence": self.evidence,
            "action": self.action,
            "pattern_id": self.pattern_id,
        }
