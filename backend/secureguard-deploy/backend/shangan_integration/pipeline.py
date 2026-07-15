"""
pipeline.py — 上安中台统一编排（:9000 FastAPI，中间件模式）

它就是 spec 任务1 里「已有，需扩展」的那个端点：
    POST /v1/openai/chat/completions
对外保持 OpenAI 兼容（Kun 的 Provider 直接指过来，零改动）；
对内把三样能力按顺序串起来：

  收到请求
    │
    ├─ guard_input           v1.0 SecureGuard 入站：敏感词/PII → 拦截或脱敏
    ├─ ExpertRouter.route    L1规则 → L2语义 → L3确认，注入 Skill System Prompt
    ├─ SemanticCache.lookup  命中(同路由+相似>0.95) → 直接返回，不调模型
    ├─ grounding.retrieve+inject  v1.0 RAG：检索切片+宪法规则，注入来源[S#]，要求引用
    ├─ TokenSaver.pre        L3结果压缩 → L5上下文压缩 → L1前缀固化 → L2工具收起
    ├─ infer()               调上游真实模型（MechDistill 7B / deepseek-v4-*）
    ├─ guard_output          v1.0 SecureGuard 出站审核 → 拦截或脱敏（在抽 artifact 之前）
    ├─ append_sources        v1.0 自动引用：实际引用的来源整理成「参考来源」
    ├─ extract_artifacts     抽取 artifact 到扩展字段
    ├─ SemanticCache.store   写回缓存
    └─ 返回 OpenAI 兼容响应（+ x_shangan_artifacts）

不修改 OpenClaw 源码：这一层独立进程，OpenClaw Gateway(:18789) 与 Kun 都把
base_url 指到本服务即可。上游模型地址由 MODEL_UPSTREAM 指向「裸模型服务」，
避免本端点自调用造成递归。
"""
from __future__ import annotations

import os
import time
import uuid

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .artifacts import attach_to_response, extract_artifacts
from .expert_router import ExpertRegistry, ExpertRouter
from .token_saver import Deps, SaverStats, TokenSaver
from . import guards
from . import grounding

# --------------------------------------------------------------------------- #
# 配置（用环境变量，便于单机部署，无 Docker）
# --------------------------------------------------------------------------- #
MODEL_UPSTREAM = os.getenv("MODEL_UPSTREAM", "http://127.0.0.1:8001/v1")  # 裸模型服务
SKILL_BASE = os.getenv("SKILL_BASE", "/data/standards_downloads/rag/experts")
UPSTREAM_TIMEOUT = float(os.getenv("UPSTREAM_TIMEOUT", "120"))

# 章节→模型 不在这里；这是平台问答路由。模型选择按难度分级（见下）。
DIFFICULTY_MODEL = {
    "easy":   os.getenv("MODEL_FLASH", "deepseek-v4-flash"),
    "medium": os.getenv("MODEL_PRO",   "deepseek-v4-pro"),
    "hard":   os.getenv("MODEL_EXPERT","mechanical-expert"),   # MechDistill 7B 深推
}


# --------------------------------------------------------------------------- #
# 依赖装配：把你方真实的 bge-m3 / 向量库 / 摘要器接进来（这里给可替换占位）
# --------------------------------------------------------------------------- #
def build_deps() -> Deps:
    # TODO: 替换为你方真实实现
    #   embed = lambda t: bge_m3.encode(t).tolist()
    #   semantic_cache_store = LanceDBTable("semantic_cache")
    #   summarize = your_summarizer
    #
    # 同时把 v1.0 能力的回调接上（不接则安全降级）：
    #   guards.SECUREGUARD_CHECK = lambda text, stage: secureguard_client.check(text, stage)
    #   grounding.RAG_SEARCH     = lambda q, f: lancedb_rag.search(q, f)   # 22074切片+宪法+标准
    #   mcp_server.RAG_SEARCH    = grounding.RAG_SEARCH                    # 知识MCP共用同一检索
    #   mcp_server.EVA_TASKS     = eva_engine.handle
    return Deps(embed=None, semantic_cache_store=None, summarize=None)


deps = build_deps()
saver = TokenSaver(deps)
registry = ExpertRegistry(SKILL_BASE, embed=deps.embed).load()
router_engine = ExpertRouter(registry, embed=deps.embed, llm_confirm=None)

api = APIRouter()


async def infer(model: str, request: dict, extra_headers: dict) -> dict:
    """调上游裸模型，OpenAI 兼容。"""
    payload = dict(request, model=model, stream=False)
    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client:
        r = await client.post(
            f"{MODEL_UPSTREAM}/chat/completions",
            json=payload,
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ.get('DEEPSEEK_API_KEY', ''), **extra_headers},
        )
        r.raise_for_status()
        return r.json()


def _last_user(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return str(m.get("content", ""))
    return ""


@api.post("/v2/chat/completions")
async def chat_completions(request: Request) -> JSONResponse:
    body = await request.json()
    conv_id = request.headers.get("X-Conversation-Id", "anon")
    stats = SaverStats()
    messages = body.get("messages", [])

    # 0) SecureGuard 入站（v1.0）：敏感词/PII → 拦截或脱敏
    messages, gin = guards.guard_input(messages)
    if gin.action == guards.Action.BLOCK:
        return JSONResponse(guards.blocked_response(gin.reason, "input"))

    # 1) 专家路由 + Skill 注入（先于省 Token，因为注入会改变 system 段）
    route = router_engine.route(_last_user(messages))
    rkey = router_engine.route_key(route)
    if route.injected_system:
        messages = [{"role": "system", "content": route.injected_system}] + [
            m for m in messages if m.get("role") != "system"
        ]

    # 2) 语义缓存命中？（同路由 + 相似度>0.95）。命中即省掉检索与推理
    cached = saver.semantic.lookup(messages, rkey, stats)
    if cached is not None:
        cached = dict(cached); cached["x_shangan_cache"] = "hit"
        return JSONResponse(cached)

    # 3) RAG grounding（v1.0）：检索切片+宪法规则 → 注入来源[S#]，要求按编号引用
    sources = grounding.retrieve(_last_user(messages), [e.id for e in route.experts])
    messages = grounding.inject(messages, sources)
    body = dict(body, messages=messages)

    # 4) 省 Token 预处理（L3/L5/L1/L2）
    body = saver.pre(body, stats)

    # 5) 难度分级 → 选模型（Kimi 渐进推理：简单走 flash，难走深推）
    _sel = body.get("model")
    model = _sel if _sel and _sel != "builtin" else DIFFICULTY_MODEL.get(route.difficulty, DIFFICULTY_MODEL["medium"])

    # 6) 调上游模型
    headers = saver.prefix.upstream_headers(stats)
    try:
        resp = await infer(model, body, headers)
    except httpx.HTTPError as e:
        return JSONResponse(
            {"error": {"message": f"upstream model error: {e}", "type": "upstream_error"}},
            status_code=502,
        )

    # 7) SecureGuard 出站审核（v1.0）：在抽 artifact 之前，确保 artifact 也来自合规文本
    content = resp.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
    gout = guards.guard_output(content)
    if gout.action == guards.Action.BLOCK:
        return JSONResponse(guards.blocked_response(gout.reason, "output"))
    if gout.action == guards.Action.SANITIZE:
        content = gout.text

    # 8) 自动引用（v1.0）：把实际引用到的来源附成「参考来源」
    content = grounding.append_sources(content, sources)

    # 9) Artifacts 抽取
    cleaned, arts = extract_artifacts(content)
    resp = attach_to_response(resp, arts, cleaned)

    # 10) 写回语义缓存 + 路由观测
    saver.semantic.store(messages, rkey, resp, stats)
    resp["x_shangan_meta"] = {
        "route_level": route.level,
        "experts": [e.id for e in route.experts],
        "difficulty": route.difficulty,
        "model": model,
        "prefix_hash": stats.prefix_hash,
        "tool_chars_saved": stats.tool_payload_saved_chars,
        "ctx_compressed": bool(stats.context_compressed_from),
        "storm_blocked": stats.storm_blocked,
        "sources": len(sources),
        "secureguard": {"in": gin.action.value, "out": gout.action.value,
                        "degraded": gin.degraded or gout.degraded},
        "artifacts": len(arts),
    }
    return JSONResponse(resp)


# --------------------------------------------------------------------------- #
# 工具按需加载的回填端点（L2 LazyTools 配套，OpenClaw Agent 会调）
# --------------------------------------------------------------------------- #
@api.post("/v2/tool_search")
async def tool_search(request: Request) -> JSONResponse:
    body = await request.json()
    return JSONResponse({"results": saver.lazy.search(body.get("keywords", []))})


@api.post("/v2/tool_describe")
async def tool_describe(request: Request) -> JSONResponse:
    body = await request.json()
    schema = saver.lazy.describe(body.get("name", ""))
    return JSONResponse(schema or {"error": "not found"})


# --------------------------------------------------------------------------- #
# 挂载方式（在你现有 :9000 app 上加一行）：
#   from shangan_integration.pipeline import api as shangan_api
#   app.include_router(shangan_api)
# 若已有同名 /v1/openai/chat/completions，把旧 handler 改名为裸转发，
# 由 MODEL_UPSTREAM 指向它即可，无需删除旧逻辑。
# --------------------------------------------------------------------------- #
