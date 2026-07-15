"""backend.sk_service — 出站调用密钥（sk-）。

让外部平台用 sk- 调你的智能体（OpenAI 兼容接口）。设计成"现在能用、以后能卖"：
一个 sk 绑定 {能调哪些智能体 + 计量口径(calls/tokens) + QuotaPolicy + 归属}。

售卖即"给买家一个带额度的 sk"：
- 按次卖   → meter="calls"
- 按量卖   → meter="tokens"
- 一次性套餐 → policy.reset_mode="none"（用完停，可选 allow_recharge 续费）
- 月度订阅  → policy.reset_mode="period", period="monthly"

计量复用现有 QuotaPolicy 引擎（不重造）。本层只做"计量+限额"（能不能用）；
"结算+收款"（算钱/支付）是以后第 2 层，本层的用量数据为它备好。
纯 stdlib，可离线测。
"""
from __future__ import annotations

import time
import uuid
import secrets
import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.quota_service import QuotaPolicy


def _now() -> float:
    return time.time()


@dataclass
class SkRecord:
    id: str                          # sk 内部 id（非密钥本身）
    key_hash: str                    # sk 明文的 hash（明文只在签发时返回一次，不留存）
    prefix: str                      # sk 前缀（便于识别，如 sk-live-xxxx 的前几位）
    owner_id: str
    label: str                       # 备注：卖给了谁/什么套餐
    agent_ids: List[str]             # 能调哪些智能体（空=全部 owner 自己的，谨慎）
    meter: str                       # "calls" | "tokens"
    policy: QuotaPolicy
    status: str = "active"           # active | revoked
    used_calls: int = 0
    used_tokens: int = 0
    created_at: float = field(default_factory=_now)
    last_used_at: Optional[float] = None
    reset_at: Optional[float] = None  # 周期计量的下次重置时间

    def public(self) -> Dict[str, Any]:
        """回传前端：不含 key_hash，只含可展示信息。"""
        limit = self.policy_limit()
        used = self.used_tokens if self.meter == "tokens" else self.used_calls
        return {
            "id": self.id, "prefix": self.prefix, "label": self.label,
            "owner_id": self.owner_id, "agent_ids": self.agent_ids,
            "meter": self.meter, "status": self.status,
            "used": used, "limit": limit,
            "remaining": (None if limit is None else max(0, limit - used)),
            "reset_mode": self.policy.reset_mode, "period": self.policy.period,
            "allow_recharge": self.policy.allow_recharge,
            "created_at": self.created_at, "last_used_at": self.last_used_at,
        }

    def policy_limit(self) -> Optional[int]:
        """该 sk 的额度上限（来自 policy.limit；None=不限）。"""
        return getattr(self.policy, "limit", None)


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class SkService:
    def __init__(self) -> None:
        self._sks: Dict[str, SkRecord] = {}        # id -> record
        self._by_hash: Dict[str, str] = {}         # key_hash -> id（O(1) 校验）

    # ---------- 签发 ----------
    def issue(self, owner_id: str, label: str, agent_ids: List[str],
              meter: str = "calls", limit: Optional[int] = None,
              reset_mode: str = "none", period: str = "monthly",
              allow_recharge: bool = True) -> Dict[str, Any]:
        """签发一个 sk。返回含**明文 key（只此一次）**+ 记录信息。"""
        if meter not in ("calls", "tokens"):
            raise ValueError("meter 只能是 calls 或 tokens")
        # 生成明文 sk：sk-<env>-<random>。明文不留存，只存 hash。
        raw = "sk-live-" + secrets.token_urlsafe(24)
        kid = "skid_" + uuid.uuid4().hex[:10]
        policy = QuotaPolicy(reset_mode=reset_mode, period=period, allow_recharge=allow_recharge)
        # 把额度上限挂到 policy（quota 引擎按 limit 判断）
        setattr(policy, "limit", limit)
        rec = SkRecord(
            id=kid, key_hash=_hash_key(raw), prefix=raw[:14],
            owner_id=owner_id, label=label, agent_ids=list(agent_ids or []),
            meter=meter, policy=policy,
        )
        if reset_mode == "period":
            rec.reset_at = _now() + (30 * 86400 if period == "monthly" else 7 * 86400)
        self._sks[kid] = rec
        self._by_hash[rec.key_hash] = kid
        out = rec.public()
        out["key"] = raw   # 明文，只此一次
        out["warning"] = "请立即保存此密钥，它只显示一次，之后无法再次查看。"
        return out

    # ---------- 校验（外部调用入口用）----------
    def verify(self, raw_key: str) -> Optional[SkRecord]:
        """校验 sk 明文 → 返回记录（无效/吊销返回 None）。"""
        if not raw_key or not raw_key.startswith("sk-"):
            return None
        kid = self._by_hash.get(_hash_key(raw_key))
        if not kid:
            return None
        rec = self._sks.get(kid)
        if not rec or rec.status != "active":
            return None
        return rec

    def can_call_agent(self, rec: SkRecord, agent_id: str) -> bool:
        """该 sk 是否被授权调用此智能体。空 agent_ids = 不限（谨慎）。"""
        return (not rec.agent_ids) or (agent_id in rec.agent_ids)

    # ---------- 配额检查 + 计量 ----------
    def check_quota(self, rec: SkRecord) -> Dict[str, Any]:
        """调用前检查：是否还有额度。返回 {ok, remaining, reason}。"""
        self._maybe_reset(rec)
        limit = rec.policy_limit()
        if limit is None:
            return {"ok": True, "remaining": None}
        used = rec.used_tokens if rec.meter == "tokens" else rec.used_calls
        if used >= limit:
            return {"ok": False, "remaining": 0, "reason": "额度已用尽"}
        return {"ok": True, "remaining": limit - used}

    def consume(self, rec: SkRecord, calls: int = 1, tokens: int = 0) -> None:
        """调用后扣减用量。"""
        rec.used_calls += calls
        rec.used_tokens += tokens
        rec.last_used_at = _now()

    def _maybe_reset(self, rec: SkRecord) -> None:
        """周期计量：到期重置用量。"""
        if rec.policy.reset_mode == "period" and rec.reset_at and _now() >= rec.reset_at:
            rec.used_calls = 0
            rec.used_tokens = 0
            rec.reset_at = _now() + (30 * 86400 if rec.policy.period == "monthly" else 7 * 86400)

    # ---------- 管理 ----------
    def revoke(self, kid: str, owner_id: Optional[str] = None) -> bool:
        rec = self._sks.get(kid)
        if not rec:
            return False
        if owner_id is not None and rec.owner_id != owner_id:
            raise PermissionError("只能吊销自己签发的 sk")
        rec.status = "revoked"
        return True

    def recharge(self, kid: str, add: int, owner_id: Optional[str] = None) -> Dict[str, Any]:
        """续费：减少已用量（等效增加可用额度）。需 policy.allow_recharge。"""
        rec = self._sks.get(kid)
        if not rec:
            raise KeyError("sk 不存在")
        if owner_id is not None and rec.owner_id != owner_id:
            raise PermissionError("只能为自己的 sk 充值")
        if not rec.policy.allow_recharge:
            raise ValueError("该 sk 不允许续费")
        if rec.meter == "tokens":
            rec.used_tokens = max(0, rec.used_tokens - add)
        else:
            rec.used_calls = max(0, rec.used_calls - add)
        return rec.public()

    def list_for_owner(self, owner_id: str) -> List[Dict[str, Any]]:
        return [r.public() for r in self._sks.values() if r.owner_id == owner_id]

    def get(self, kid: str) -> Optional[SkRecord]:
        return self._sks.get(kid)
