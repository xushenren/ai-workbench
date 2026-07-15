"""backend.factory — 按配置组装 AppState（B7）。

无环境变量 → 全内存(可测，沙箱/开发用)；设了环境变量 → 切真实后端(真机)。
工厂是 B7 的核心价值：把"用哪个后端"集中到一处，业务代码与端点层完全不感知。
"""
from __future__ import annotations

from typing import Optional

from secureguard import Orchestrator, RAGPipeline, InMemoryVectorStore, MockModel, Doc
from .state import AppState
from .quota_service import QuotaService
from .settings import Settings


def _seed_inmemory_store() -> InMemoryVectorStore:
    store = InMemoryVectorStore()
    store.add(Doc("doc_1", "风管安装验收应符合 GB50243 相关条款，漏风率需达标。", {"trust_score": 0.9}))
    store.add(Doc("doc_2", "隐蔽工程验收需在覆盖前完成，留存影像与记录。", {"trust_score": 0.85}))
    store.add(Doc("doc_3", "幂等性指同一操作执行多次与一次结果一致。", {"trust_score": 0.8}))
    return store


def build_state(settings: Optional[Settings] = None) -> AppState:
    """根据配置选后端。未配置项回落内存版。"""
    s = settings or Settings.from_env()

    # ---- 模型 ----
    if s.use_real_model:
        from .adapters import VLLMModel
        model = VLLMModel(s.model_base_url, s.model_name, s.model_api_key)
    else:
        model = MockModel()

    # ---- 向量库 ----
    if s.use_chroma:
        from .adapters import ChromaVectorStore
        store = ChromaVectorStore(s.chroma_host, s.chroma_port)
    else:
        store = _seed_inmemory_store()

    orchestrator = Orchestrator(rag=RAGPipeline(store, model))

    # ---- 配额 ----
    if s.use_redis:
        from .adapters import RedisQuotaService
        quota = RedisQuotaService(s.redis_url)
    else:
        quota = QuotaService()

    state = AppState(orchestrator=orchestrator, quota=quota)

    # ---- 身份桥接：org_core 成为新能力的身份权威 ----
    import os
    from backend.identity_service import IdentityService
    from org_core import SqliteRepos
    state.identity = IdentityService(
        state.auth,
        org_repo=SqliteRepos(os.path.join(os.getenv("DATA_DIR", "./data"), "org_core.db")),
    )

    # ---- Postgres / 微信：仓储已在 adapters.pg_repos 提供，接入指引见该文件。
    # 此处不强行重构 Auth/Agent/KB 服务（需仓储注入），保持内存版可跑；
    # 生产接 PG 时把这些服务内部 dict 换成仓储调用即可（对外签名不变）。

    return state
