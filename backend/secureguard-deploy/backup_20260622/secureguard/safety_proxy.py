"""secureguard.safety_proxy — 安全代理可用性保障（回答咨询 #2 的 fail-open/closed）。

把 Orchestrator 包成一个对外的安全代理，并解决"代理自己挂了怎么办"：

  - fail-closed（默认）：守卫超时/异常 → 默认 BLOCK。安全代理的存在意义是"挡住坏的"，
    它失效时若放行（fail-open），等于把防线关掉。所以安全场景默认 fail-closed。
  - 超时：单次处理设硬超时，避免被慢请求拖垮。
  - 熔断：连续失败累计到阈值 → 打开断路器，进入冷却；冷却后半开试探。断路器打开期间
    直接按 fail 策略短路，不再打底层（保护下游、避免雪崩）。

何时可选 fail-open：仅当"可用性 > 安全"且后端本身可信（例如内部只读问答），
可显式配置 fail_policy="open"，但必须是明确决策而非默认。纯标准库 + asyncio。
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ProxyConfig:
    timeout_s: float = 5.0
    fail_policy: str = "closed"        # closed=失败则拒绝 / open=失败则放行
    breaker_threshold: int = 5         # 连续失败多少次打开断路器
    breaker_cooldown_s: float = 30.0   # 断路器冷却时长


class _CircuitBreaker:
    """三态断路器：closed → open → half_open → closed。"""

    def __init__(self, threshold: int, cooldown_s: float) -> None:
        self.threshold = threshold
        self.cooldown_s = cooldown_s
        self.fails = 0
        self.state = "closed"
        self.opened_at = 0.0

    def allow(self) -> bool:
        if self.state == "open":
            if time.monotonic() - self.opened_at >= self.cooldown_s:
                self.state = "half_open"
                return True       # 放一个试探请求
            return False
        return True

    def on_success(self) -> None:
        self.fails = 0
        self.state = "closed"

    def on_failure(self) -> None:
        self.fails += 1
        if self.fails >= self.threshold:
            self.state = "open"
            self.opened_at = time.monotonic()


class SafetyProxy:
    """对外安全代理。包裹任意拥有 async process(...) 的协调器。"""

    def __init__(self, orchestrator: Any, config: Optional[ProxyConfig] = None) -> None:
        self.orch = orchestrator
        self.cfg = config or ProxyConfig()
        self.breaker = _CircuitBreaker(self.cfg.breaker_threshold, self.cfg.breaker_cooldown_s)

    def _fail_result(self, stage: str, reason: str) -> Dict[str, Any]:
        if self.cfg.fail_policy == "open":
            # 显式选择的可用性优先：放行但标注降级
            return {"blocked": False, "degraded": True, "stage": stage,
                    "reason": reason, "answer": "", "note": "fail-open degraded passthrough"}
        # 默认 fail-closed：拒绝
        return {"blocked": True, "degraded": True, "stage": stage,
                "reason": reason, "message": "安全代理暂不可用，已按 fail-closed 拒绝。"}

    async def process(self, user_input: str, session_id: str = "anon",
                      action: Optional[Dict[str, Any]] = None,
                      ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # 断路器：打开期间直接按 fail 策略短路
        if not self.breaker.allow():
            return self._fail_result("breaker_open", "circuit breaker open")

        try:
            res = await asyncio.wait_for(
                self.orch.process(user_input, session_id, action, ctx),
                timeout=self.cfg.timeout_s,
            )
            self.breaker.on_success()
            return res
        except asyncio.TimeoutError:
            self.breaker.on_failure()
            return self._fail_result("timeout", f"exceeded {self.cfg.timeout_s}s")
        except Exception as e:  # 守卫/后端异常 → 按 fail 策略
            self.breaker.on_failure()
            return self._fail_result("error", f"{type(e).__name__}: {e}")
