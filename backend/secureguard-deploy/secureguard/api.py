"""secureguard.api — FastAPI 服务入口（协调器对外 HTTP 接口）。

依赖 fastapi + uvicorn；缺失时本模块仍可被导入（不会破坏离线测试），
仅在真正启动服务时才需要这些依赖。

启动：uvicorn secureguard.api:app --host 0.0.0.0 --port 9000
"""
from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from fastapi import FastAPI
    from pydantic import BaseModel
    _FASTAPI_OK = True
except Exception:  # pragma: no cover - 依赖缺失时的离线占位
    _FASTAPI_OK = False

from .orchestrator import Orchestrator
from .l2_reasoning import Doc, InMemoryVectorStore, MockModel, RAGPipeline


def build_default_orchestrator() -> Orchestrator:
    """构造默认协调器。生产部署时把 RAG 换成 VLLMModel + ChromaVectorStore。"""
    store = InMemoryVectorStore()
    store.add(Doc("doc_1", "幂等性指同一操作执行多次结果一致。", {"trust_score": 0.9}))
    store.add(Doc("doc_2", "RAG 通过检索可信文档为生成提供事实锚点。", {"trust_score": 0.8}))
    return Orchestrator(rag=RAGPipeline(store, MockModel()))


if _FASTAPI_OK:  # pragma: no cover - 需安装 fastapi 才执行
    app = FastAPI(title="SecureGuard", version="1.0.0")
    _orch = build_default_orchestrator()

    class ChatRequest(BaseModel):
        message: str
        session_id: str = "anon"
        action: Optional[Dict[str, Any]] = None
        ctx: Optional[Dict[str, Any]] = None

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/chat")
    async def chat(req: ChatRequest) -> Dict[str, Any]:
        """端到端跑五层门控并返回结果（含逐层轨迹）。"""
        return await _orch.process(req.message, req.session_id, req.action, req.ctx)

    @app.get("/v1/audit/summary")
    async def audit_summary() -> Dict[str, Any]:
        return _orch.auditor.summary()
else:
    app = None  # 离线环境占位，导入不报错
