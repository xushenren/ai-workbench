"""
mcp_server.py — Kun 桌面通过 MCP 接上安能力（spec 任务6）

Kun 端配置两个 MCP Server：
  shangan-knowledge → /v1/mcp/knowledge   知识检索（RAG + 标准条文 + 因果链）
  shangan-tasks     → /v1/mcp/tasks       EVA 任务（派单/日报/监控）

这里用 HTTP + MCP 工具清单的形式实现（MCP over HTTP），挂在同一个 :9000 app 上。
若你方用官方 mcp SDK 的 stdio/SSE 模式，把 handler 内部逻辑原样搬过去即可——
工具 schema 与处理函数是与传输无关的。
"""
from __future__ import annotations

import os
from typing import Any, Callable, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

mcp = APIRouter()

# 你方真实检索/任务实现注入点（缺省返回占位，便于先连通再填肉）
RAG_SEARCH: Optional[Callable[[str, dict], list[dict]]] = None    # (query, filters)->slices
EVA_TASKS: Optional[Callable[[str, dict], Any]] = None            # (action, args)->result


# --------------------------------------------------------------------------- #
# 工具清单（Kun 启动时拉取，决定可调用的工具）
# --------------------------------------------------------------------------- #
KNOWLEDGE_TOOLS = [
    {
        "name": "knowledge_search",
        "description": "检索机电安装知识库：施工方案/标准条文/因果链。可按专业、行业、标准号过滤。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "skill_id": {"type": "string", "description": "限定专业，如 01管道/02电气"},
                "industry": {"type": "string", "description": "限定行业，如 医院/数据中心"},
                "standards_ref": {"type": "string", "description": "限定标准号"},
                "top_k": {"type": "integer", "default": 6},
            },
            "required": ["query"],
        },
    },
    {
        "name": "standard_lookup",
        "description": "按标准号或关键词查标准条文原文（top50核心 + 152补充）。",
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string"}, "keyword": {"type": "string"}},
        },
    },
]

TASK_TOOLS = [
    {
        "name": "eva_list_tasks",
        "description": "列出 EVA 引擎当前任务（派单/巡检/日报）。",
        "inputSchema": {"type": "object", "properties": {"status": {"type": "string"}}},
    },
    {
        "name": "eva_create_task",
        "description": "创建一个 EVA 任务（定时扫描/派单/监控）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["scan", "dispatch", "report", "monitor"]},
                "target": {"type": "string"},
                "schedule": {"type": "string", "description": "cron 或自然语言"},
            },
            "required": ["kind", "target"],
        },
    },
]


def _ok(result: Any) -> dict:
    # MCP tools/call 返回约定
    return {"content": [{"type": "text", "text": result if isinstance(result, str) else _json(result)}]}


def _json(x: Any) -> str:
    import json
    return json.dumps(x, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# knowledge server
# --------------------------------------------------------------------------- #
@mcp.get("/v1/mcp/knowledge")
async def knowledge_manifest() -> JSONResponse:
    return JSONResponse({"name": "shangan-knowledge", "tools": KNOWLEDGE_TOOLS})


@mcp.post("/v1/mcp/knowledge")
async def knowledge_call(request: Request) -> JSONResponse:
    body = await request.json()
    name, args = body.get("name"), body.get("arguments", {})
    if name == "knowledge_search":
        if RAG_SEARCH:
            filters = {k: args[k] for k in ("skill_id", "industry", "standards_ref") if args.get(k)}
            hits = RAG_SEARCH(args["query"], filters)
        else:
            hits = [{"note": "RAG_SEARCH 未接入，返回占位", "query": args.get("query")}]
        return JSONResponse(_ok(hits))
    if name == "standard_lookup":
        if RAG_SEARCH:
            hits = RAG_SEARCH(args.get("keyword") or args.get("ref", ""), {"source_type": "standard"})
        else:
            hits = [{"note": "standard 检索未接入"}]
        return JSONResponse(_ok(hits))
    return JSONResponse({"error": f"unknown tool: {name}"}, status_code=400)


# --------------------------------------------------------------------------- #
# tasks server
# --------------------------------------------------------------------------- #
@mcp.get("/v1/mcp/tasks")
async def tasks_manifest() -> JSONResponse:
    return JSONResponse({"name": "shangan-tasks", "tools": TASK_TOOLS})


@mcp.post("/v1/mcp/tasks")
async def tasks_call(request: Request) -> JSONResponse:
    body = await request.json()
    name, args = body.get("name"), body.get("arguments", {})
    action = {"eva_list_tasks": "list", "eva_create_task": "create"}.get(name)
    if not action:
        return JSONResponse({"error": f"unknown tool: {name}"}, status_code=400)
    result = EVA_TASKS(action, args) if EVA_TASKS else {"note": "EVA_TASKS 未接入", "action": action, "args": args}
    return JSONResponse(_ok(result))


# 挂载：app.include_router(mcp)
