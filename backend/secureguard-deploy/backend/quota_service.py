"""backend.quota_service — 配额与计费（B4，框架无关核心）。

D6 配额模型：
    免费额度(如 10K/月)
      ↓ 用完
    允许负数(不中断当前请求) —— 跨过阈值的那一次请求照常完成
      ↓ 余额 ≤ 0
    锁定该智能体(对此用户)
      ↓
    等冻结时间到(下月重置) 或 充值 → 立即解锁

并发安全：用 asyncio.Lock 保护"读-改-写"临界区。临界区内故意留一个 await 让出点，
证明**有锁则不丢更新**(无锁会透支)。生产换 Redis DECRBY + Lua 脚本，语义一致。
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

Key = Tuple[str, str]  # (user_id, agent_id)


@dataclass
class QuotaPolicy:
    """可组合的配额策略（admin 设，产品级）。三个维度自由组合：

    reset_mode —— 额度用尽后怎么恢复：
        "period"   按周期重置（monthly/weekly）——免费额度每月/周回满
        "cooldown" 冷却锁定 cooldown_seconds 后自动解锁（类 Claude 临时锁，时长 admin 定）
        "none"     硬停，不自动恢复，只能靠充值（类 DeepSeek 用完即停）
    allow_recharge —— 是否允许充值续命（False=免费额度用完彻底停，无法充值续）
    """
    reset_mode: str = "period"     # period | cooldown | none
    period: str = "monthly"        # period 模式：monthly | weekly
    cooldown_seconds: int = 3600   # cooldown 模式：锁定时长
    allow_recharge: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ConsumeResult:
    allowed: bool
    remaining: int
    used: int
    locked: bool
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


def _next_month_first(now_epoch: float) -> float:
    """下月 1 日 00:00 UTC 的时间戳（"下月1日重置"）。"""
    dt = datetime.fromtimestamp(now_epoch, tz=timezone.utc)
    year, month = (dt.year + 1, 1) if dt.month == 12 else (dt.year, dt.month + 1)
    return datetime(year, month, 1, tzinfo=timezone.utc).timestamp()


class QuotaService:
    """内存配额服务。clock 可注入便于测试冻结/重置。生产换 Redis。"""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._rec: Dict[Key, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._clock = clock
        self._policies: Dict[str, QuotaPolicy] = {}  # agent_id -> 策略

    # ---------- 策略注册（admin 设，每个智能体一套） ----------
    def set_policy(self, agent_id: str, policy: QuotaPolicy) -> None:
        self._policies[agent_id] = policy

    def get_policy(self, agent_id: str) -> Optional[QuotaPolicy]:
        return self._policies.get(agent_id)

    def _resolve_policy(self, key: Key, freeze_period: str,
                        policy: Optional[QuotaPolicy]) -> QuotaPolicy:
        if policy is not None:
            return policy
        if key[1] in self._policies:
            return self._policies[key[1]]
        # 向后兼容旧的 freeze_period 字符串
        if freeze_period in ("monthly", "weekly"):
            return QuotaPolicy(reset_mode="period", period=freeze_period)
        if freeze_period == "none":
            return QuotaPolicy(reset_mode="none")
        return QuotaPolicy()

    def _ensure(self, key: Key, limit: int) -> Dict[str, Any]:
        if key not in self._rec:
            self._rec[key] = {"used": 0, "limit": limit, "locked": False, "freeze_until": None}
        return self._rec[key]

    def _maybe_reset(self, rec: Dict[str, Any]) -> None:
        """到了冻结/冷却重置点 → 清零并解锁。"""
        fu = rec["freeze_until"]
        if fu is not None and self._clock() >= fu:
            rec["used"] = 0
            rec["locked"] = False
            rec["freeze_until"] = None

    def _freeze_target(self, pol: QuotaPolicy) -> Optional[float]:
        """按策略算"何时自动解锁"。period=周期边界；cooldown=now+时长；none=永不（仅充值）。"""
        if pol.reset_mode == "period":
            return _next_month_first(self._clock()) if pol.period == "monthly" else self._clock() + 7 * 86400
        if pol.reset_mode == "cooldown":
            return self._clock() + pol.cooldown_seconds
        return None  # none：硬停，不自动恢复

    # ---------- 扣减（原子） ----------
    async def consume(self, key: Key, tokens: int, limit: int = 10000,
                      freeze_period: str = "monthly",
                      policy: Optional[QuotaPolicy] = None) -> ConsumeResult:
        async with self._lock:
            pol = self._resolve_policy(key, freeze_period, policy)
            rec = self._ensure(key, limit)
            self._maybe_reset(rec)
            if rec["locked"]:
                return ConsumeResult(False, rec["limit"] - rec["used"], rec["used"], True, "quota_locked")
            await asyncio.sleep(0)            # 让出点——有锁才不会在此被并发插队
            rec["used"] += tokens
            if rec["used"] >= rec["limit"]:
                rec["locked"] = True
                rec["freeze_until"] = self._freeze_target(pol)
            return ConsumeResult(True, rec["limit"] - rec["used"], rec["used"], rec["locked"])

    # ---------- 查询 ----------
    async def status(self, key: Key, limit: int = 10000,
                     freeze_period: str = "monthly",
                     policy: Optional[QuotaPolicy] = None) -> Dict[str, Any]:
        async with self._lock:
            pol = self._resolve_policy(key, freeze_period, policy)
            rec = self._ensure(key, limit)
            self._maybe_reset(rec)
            return {
                "used": rec["used"], "limit": rec["limit"],
                "remaining": rec["limit"] - rec["used"],
                "locked": rec["locked"], "freeze_until": rec["freeze_until"],
                "freeze_period": pol.period if pol.reset_mode == "period" else pol.reset_mode,
                "policy": pol.to_dict(),
            }

    # ---------- 充值 / 解锁 / 管理调整 ----------
    async def recharge(self, key: Key, add_tokens: int,
                       policy: Optional[QuotaPolicy] = None) -> Dict[str, Any]:
        """充值：提高额度并立即解锁。若策略 allow_recharge=False（如纯免费档）→ 拒绝。"""
        async with self._lock:
            pol = self._resolve_policy(key, "monthly", policy)
            rec = self._ensure(key, add_tokens)
            if not pol.allow_recharge:
                return {"limit": rec["limit"], "remaining": rec["limit"] - rec["used"],
                        "locked": rec["locked"], "allowed": False, "reason": "recharge_disabled"}
            rec["limit"] += add_tokens
            rec["locked"] = False
            rec["freeze_until"] = None
            return {"limit": rec["limit"], "remaining": rec["limit"] - rec["used"],
                    "locked": False, "allowed": True}

    async def set_limit(self, key: Key, new_limit: int) -> Dict[str, Any]:
        """管理员调整额度（权限校验在端点层用 permissions.can_manage_quota）。"""
        async with self._lock:
            rec = self._ensure(key, new_limit)
            rec["limit"] = new_limit
            rec["locked"] = rec["used"] >= new_limit
            return {"limit": rec["limit"], "remaining": rec["limit"] - rec["used"], "locked": rec["locked"]}
