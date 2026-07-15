"""backend.adapters.redis_quota — 真实配额(Redis 原子扣减)。

⚠️ 未在沙箱测试：需 Redis。接口与 backend.QuotaService 完全一致
（consume / status / recharge / set_limit），工厂里 swap 是配置级。

原子性：consume 用单条 Lua 脚本完成"读锁→INCRBY→判阈值→置锁"，Redis 单线程执行
脚本天然原子，无竞态(比内存版的 asyncio.Lock 更强，适合多进程/多实例)。
月度重置：对计数键 EXPIREAT 到下月 1 日，到点自动消失即清零。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from backend.quota_service import ConsumeResult

Key = Tuple[str, str]

# Lua：原子 check-and-consume。KEYS=[used, locked] ARGV=[tokens, limit]
_CONSUME_LUA = """
if redis.call('GET', KEYS[2]) == '1' then
  return {0, tonumber(redis.call('GET', KEYS[1]) or '0'), 1}
end
local used = tonumber(redis.call('INCRBY', KEYS[1], ARGV[1]))
local locked = 0
if used >= tonumber(ARGV[2]) then
  redis.call('SET', KEYS[2], '1')
  locked = 1
end
return {1, used, locked}
"""


def _next_month_epoch() -> int:
    dt = datetime.now(timezone.utc)
    y, m = (dt.year + 1, 1) if dt.month == 12 else (dt.year, dt.month + 1)
    return int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp())


class RedisQuotaService:
    """QuotaService 的真实替身（Redis 后端）。"""

    def __init__(self, url: str) -> None:
        try:
            import redis.asyncio as aioredis  # 懒加载
        except Exception as e:  # pragma: no cover
            raise RuntimeError("RedisQuotaService 需要 redis：pip install redis") from e
        self._r = aioredis.from_url(url, decode_responses=True)
        self._consume = self._r.register_script(_CONSUME_LUA)

    @staticmethod
    def _keys(key: Key) -> Tuple[str, str]:
        u, a = key
        return f"quota:{u}:{a}:used", f"quota:{u}:{a}:locked"

    async def consume(self, key: Key, tokens: int, limit: int = 10000,
                      freeze_period: str = "monthly") -> ConsumeResult:  # pragma: no cover
        ku, kl = self._keys(key)
        allowed, used, locked = await self._consume(keys=[ku, kl], args=[tokens, limit])
        if locked and freeze_period == "monthly":
            await self._r.expireat(ku, _next_month_epoch())
            await self._r.expireat(kl, _next_month_epoch())
        return ConsumeResult(bool(allowed), limit - int(used), int(used), bool(locked),
                             "quota_locked" if not allowed else "")

    async def status(self, key: Key, limit: int = 10000,
                     freeze_period: str = "monthly") -> Dict[str, Any]:  # pragma: no cover
        ku, kl = self._keys(key)
        used = int(await self._r.get(ku) or 0)
        locked = (await self._r.get(kl)) == "1"
        return {"used": used, "limit": limit, "remaining": limit - used,
                "locked": locked, "freeze_until": None, "freeze_period": freeze_period}

    async def recharge(self, key: Key, add_tokens: int) -> Dict[str, Any]:  # pragma: no cover
        ku, kl = self._keys(key)
        await self._r.delete(kl)                       # 解锁
        used = int(await self._r.get(ku) or 0)
        return {"limit": add_tokens, "remaining": add_tokens - used, "locked": False}

    async def set_limit(self, key: Key, new_limit: int) -> Dict[str, Any]:  # pragma: no cover
        ku, kl = self._keys(key)
        used = int(await self._r.get(ku) or 0)
        locked = used >= new_limit
        if locked:
            await self._r.set(kl, "1")
        else:
            await self._r.delete(kl)
        return {"limit": new_limit, "remaining": new_limit - used, "locked": locked}
