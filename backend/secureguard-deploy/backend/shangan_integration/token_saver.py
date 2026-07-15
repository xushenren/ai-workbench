"""
token_saver.py — Kun 省Token 方法论的 6 层实现（中间件模式，不改 OpenClaw 源码）

落点：消息进入模型前/出模型后，由 pipeline.py 串联调用。
每层都是独立、可单独开关的 Stage，便于按 spec 的「阶段1 先上前3层」分批落地。

依赖（你方应已具备）：
  - httpx（异步调上游模型）
  - 一个 embedding 函数 embed(text)->list[float]（bge-m3），由 deps 注入
  - 一个向量存储（LanceDB/Chroma），这里用可替换的 VectorStore 协议
所有外部依赖都通过 Deps 注入，未接通时降级为安全 no-op，不会阻断主链路。
"""
from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

Message = dict[str, Any]


# --------------------------------------------------------------------------- #
# 依赖注入：把你方真实的 embedding / 向量库 / 摘要模型接进来
# --------------------------------------------------------------------------- #
class VectorStore(Protocol):
    def query(self, vector: list[float], top_k: int) -> list[dict]: ...
    def add(self, vector: list[float], payload: dict) -> None: ...


@dataclass
class Deps:
    embed: Optional[Callable[[str], list[float]]] = None        # bge-m3
    semantic_cache_store: Optional[VectorStore] = None          # LanceDB table
    summarize: Optional[Callable[[list[Message]], str]] = None  # 长会话摘要器（小模型）
    now: Callable[[], float] = time.time


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _est_tokens(messages: list[Message]) -> int:
    # 粗估：中文按 ~1.6 char/token，英文按 ~4 char/token，混合取中值 2.0
    chars = sum(len(str(m.get("content", ""))) for m in messages)
    return int(chars / 2.0)


@dataclass
class SaverStats:
    prefix_hash: Optional[str] = None
    semantic_cache_hit: bool = False
    context_compressed_from: int = 0
    context_compressed_to: int = 0
    storm_blocked: bool = False
    tool_payload_saved_chars: int = 0


# --------------------------------------------------------------------------- #
# L1 前缀固化：System Prompt SHA256 → 命中上游 prompt caching
# --------------------------------------------------------------------------- #
class PrefixCache:
    """不自己缓存，而是把 system 段稳定化 + 打标，让上游（vLLM/sglang）的
    prefix caching 命中。判据：system 内容字节级不变 → 同一 hash → 上游复用 KV。"""

    def stabilize(self, messages: list[Message], stats: SaverStats) -> list[Message]:
        sys_msgs = [m for m in messages if m.get("role") == "system"]
        if not sys_msgs:
            return messages
        joined = "\n".join(str(m.get("content", "")) for m in sys_msgs)
        stats.prefix_hash = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]
        # 关键：system 永远排在最前且顺序固定，避免因顺序抖动导致 KV 失配
        non_sys = [m for m in messages if m.get("role") != "system"]
        return sys_msgs + non_sys

    def upstream_headers(self, stats: SaverStats) -> dict[str, str]:
        # 给上游一个稳定 cache key（若上游支持显式 prefix key）
        return {"X-Prefix-Cache-Key": stats.prefix_hash} if stats.prefix_hash else {}


# --------------------------------------------------------------------------- #
# L2 工具按需加载：tool_search -> tool_describe -> tool_call
# --------------------------------------------------------------------------- #
class LazyTools:
    """请求里若挂了一大堆完整 tool schema，先全部撤下，只暴露一个 tool_search。
    模型需要时检索 → describe 拿到单个 schema → 再 call。省掉每轮重复的全量 schema。"""

    SEARCH_TOOL = {
        "type": "function",
        "function": {
            "name": "tool_search",
            "description": "按关键词检索可用工具，返回工具名与一句话用途。需要某工具时先搜，再用 tool_describe 取其参数。",
            "parameters": {
                "type": "object",
                "properties": {"keywords": {"type": "array", "items": {"type": "string"}}},
                "required": ["keywords"],
            },
        },
    }

    def __init__(self, full_tools: list[dict] | None = None):
        # full_tools: 你方完整工具注册表；缺省为空表，stage 自动 no-op
        self._registry = {t["function"]["name"]: t for t in (full_tools or [])}

    def collapse(self, request: dict, stats: SaverStats) -> dict:
        tools = request.get("tools") or []
        if len(tools) <= 1:
            return request
        saved = sum(len(str(t)) for t in tools)
        stats.tool_payload_saved_chars += saved
        # 把注册表并入本地，替换为单个 search 工具
        for t in tools:
            self._registry.setdefault(t["function"]["name"], t)
        request = dict(request)
        request["tools"] = [self.SEARCH_TOOL]
        return request

    # 由 pipeline 在收到模型的 tool_search/tool_describe 调用时回填
    def search(self, keywords: list[str], top: int = 5) -> list[dict]:
        kws = [k.lower() for k in keywords]
        scored = []
        for name, t in self._registry.items():
            blob = (name + " " + t["function"].get("description", "")).lower()
            scored.append((sum(blob.count(k) for k in kws), name, t["function"].get("description", "")))
        scored.sort(reverse=True)
        return [{"name": n, "description": d} for s, n, d in scored[:top] if s > 0]

    def describe(self, name: str) -> dict | None:
        return self._registry.get(name)


# --------------------------------------------------------------------------- #
# L3 结果压缩：工具输出截断 + 去重
# --------------------------------------------------------------------------- #
class ResultCompress:
    def __init__(self, max_chars: int = 4000):
        self.max_chars = max_chars

    def compress(self, messages: list[Message], stats: SaverStats) -> list[Message]:
        seen: set[str] = set()
        out: list[Message] = []
        for m in messages:
            if m.get("role") != "tool":
                out.append(m)
                continue
            content = str(m.get("content", ""))
            # 去重：同一工具结果重复出现只留一次
            sig = hashlib.md5(content.encode("utf-8")).hexdigest()
            if sig in seen:
                stats.tool_payload_saved_chars += len(content)
                continue
            seen.add(sig)
            if len(content) > self.max_chars:
                stats.tool_payload_saved_chars += len(content) - self.max_chars
                head = content[: self.max_chars - 200]
                tail = content[-200:]
                content = f"{head}\n…[已截断 {len(content) - self.max_chars} 字]…\n{tail}"
            m = dict(m, content=content)
            out.append(m)
        return out


# --------------------------------------------------------------------------- #
# L4 Storm 抑制：同参数 3 次拦截 → 强制改策略
# --------------------------------------------------------------------------- #
class StormSuppressor:
    """按 (会话, 工具名, 参数) 计数，第 3 次同参调用拦截，注入一条系统提示要求换策略。"""

    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self._counter: dict[str, int] = {}

    @staticmethod
    def _key(conv_id: str, tool: str, args: Any) -> str:
        return hashlib.md5(f"{conv_id}|{tool}|{args}".encode("utf-8")).hexdigest()

    def check(self, conv_id: str, tool: str, args: Any, stats: SaverStats) -> Optional[Message]:
        k = self._key(conv_id, tool, args)
        self._counter[k] = self._counter.get(k, 0) + 1
        if self._counter[k] >= self.threshold:
            stats.storm_blocked = True
            return {
                "role": "system",
                "content": (
                    f"检测到对 `{tool}` 的相同参数重复调用已达 {self._counter[k]} 次且未取得进展。"
                    "停止重复，改变策略：换检索关键词、拆解子问题，或直接基于已有信息作答。"
                ),
            }
        return None


# --------------------------------------------------------------------------- #
# L5 上下文压缩：长会话摘要（96K→108K 区间触发）
# --------------------------------------------------------------------------- #
class ContextCompressor:
    def __init__(self, deps: Deps, trigger_tokens: int = 96_000, keep_recent: int = 6):
        self.deps = deps
        self.trigger = trigger_tokens
        self.keep_recent = keep_recent

    def maybe_compress(self, messages: list[Message], stats: SaverStats) -> list[Message]:
        total = _est_tokens(messages)
        if total < self.trigger or not self.deps.summarize:
            return messages
        sys_msgs = [m for m in messages if m.get("role") == "system"]
        body = [m for m in messages if m.get("role") != "system"]
        if len(body) <= self.keep_recent:
            return messages
        old, recent = body[: -self.keep_recent], body[-self.keep_recent :]
        summary = self.deps.summarize(old)  # 你方小模型摘要器
        stats.context_compressed_from = total
        compressed = sys_msgs + [
            {"role": "system", "content": f"[早期对话摘要]\n{summary}"}
        ] + recent
        stats.context_compressed_to = _est_tokens(compressed)
        return compressed


# --------------------------------------------------------------------------- #
# L6 语义缓存：embedding 相似度 >0.95 直接复用
# --------------------------------------------------------------------------- #
class SemanticCache:
    def __init__(self, deps: Deps, threshold: float = 0.95, ttl_sec: int = 7 * 86400):
        self.deps = deps
        self.threshold = threshold
        self.ttl = ttl_sec
        self._mem: list[tuple[list[float], dict]] = []  # 无外部库时的兜底

    def _last_user(self, messages: list[Message]) -> Optional[str]:
        for m in reversed(messages):
            if m.get("role") == "user":
                return str(m.get("content", ""))
        return None

    def lookup(self, messages: list[Message], route_key: str, stats: SaverStats) -> Optional[dict]:
        if not self.deps.embed:
            return None
        q = self._last_user(messages)
        if not q:
            return None
        vec = self.deps.embed(q)
        candidates = (
            self.deps.semantic_cache_store.query(vec, top_k=1)
            if self.deps.semantic_cache_store
            else [{"payload": p, "score": _cosine(vec, v)} for v, p in self._mem]
        )
        best = max(candidates, key=lambda c: c.get("score", 0), default=None) if candidates else None
        if best and best.get("score", 0) >= self.threshold:
            p = best["payload"]
            # 同一专家路由下才复用，避免跨 Skill 串答
            if p.get("route_key") == route_key and (self.deps.now() - p.get("ts", 0)) < self.ttl:
                stats.semantic_cache_hit = True
                return p.get("completion")
        return None

    def store(self, messages: list[Message], route_key: str, completion: dict, stats: SaverStats) -> None:
        if not self.deps.embed or stats.semantic_cache_hit:
            return
        q = self._last_user(messages)
        if not q:
            return
        vec = self.deps.embed(q)
        payload = {"route_key": route_key, "completion": completion, "ts": self.deps.now()}
        if self.deps.semantic_cache_store:
            self.deps.semantic_cache_store.add(vec, payload)
        else:
            self._mem.append((vec, payload))


# --------------------------------------------------------------------------- #
# 组合器：pipeline.py 只需持有一个 TokenSaver
# --------------------------------------------------------------------------- #
@dataclass
class TokenSaver:
    deps: Deps
    enable: dict[str, bool] = field(default_factory=lambda: {
        "L1_prefix": True, "L2_lazy_tools": True, "L3_result": True,
        "L4_storm": True, "L5_context": True, "L6_semantic": True,
    })

    def __post_init__(self):
        self.prefix = PrefixCache()
        self.lazy = LazyTools()
        self.result = ResultCompress()
        self.storm = StormSuppressor()
        self.context = ContextCompressor(self.deps)
        self.semantic = SemanticCache(self.deps)

    def pre(self, request: dict, stats: SaverStats) -> dict:
        """模型调用前的省 Token 处理（L1/L2/L3/L5）。L6 单独在 pipeline 查缓存。"""
        msgs = request.get("messages", [])
        if self.enable["L3_result"]:
            msgs = self.result.compress(msgs, stats)
        if self.enable["L5_context"]:
            msgs = self.context.maybe_compress(msgs, stats)
        if self.enable["L1_prefix"]:
            msgs = self.prefix.stabilize(msgs, stats)
        request = dict(request, messages=msgs)
        if self.enable["L2_lazy_tools"]:
            request = self.lazy.collapse(request, stats)
        return request
