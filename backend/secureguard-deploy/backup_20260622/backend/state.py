"""backend.state — 应用状态 / 依赖注入容器（B0）。

把 Orchestrator、AuditLogger、内存数据表挂在一个 AppState 上，便于：
  - FastAPI 依赖注入（每个请求拿同一个 state）；
  - 测试时整体替换（喂 Mock 后端）。

开发期数据全在内存（按计划 B0–B6 的默认），生产换 Postgres/Redis（B7）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from secureguard import (
    Orchestrator, AuditLogger, RAGPipeline, InMemoryVectorStore, MockModel, Doc,
)
from .auth import AuthService
from .agent_service import AgentService
from .quota_service import QuotaService
from .kb_service import KBService
from .user_admin_service import UserAdminService


def _seed_rag() -> RAGPipeline:
    """内置一个离线 RAG（内存库 + Mock 模型），保证无 GPU 也能端到端跑。"""
    store = InMemoryVectorStore()
    store.add(Doc("doc_1", "风管安装验收应符合 GB50243 相关条款，漏风率需达标。", {"trust_score": 0.9}))
    store.add(Doc("doc_2", "隐蔽工程验收需在覆盖前完成，留存影像与记录。", {"trust_score": 0.85}))
    store.add(Doc("doc_3", "幂等性指同一操作执行多次与一次结果一致。", {"trust_score": 0.8}))
    return RAGPipeline(store, MockModel())


@dataclass
class AppState:
    """全局应用状态。FastAPI 与测试都通过它访问内核。"""

    orchestrator: Orchestrator = field(default_factory=lambda: Orchestrator(rag=_seed_rag()))
    auditor: AuditLogger = field(default_factory=AuditLogger)
    auth: AuthService = field(default_factory=AuthService)
    agent_service: AgentService = field(default_factory=AgentService)
    quota: QuotaService = field(default_factory=QuotaService)
    kb_service: KBService = field(default_factory=KBService)
    sessions: Any = field(default=None)
    models: Any = field(default=None)
    files: Any = field(default=None)
    voice: Any = field(default=None)
    # 简易内存用户表（与 auth 解耦的业务侧信息，B5 会用）。
    users: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    user_admin: Any = field(default=None)

    def __post_init__(self) -> None:
        # 让 orchestrator 与 state 共享同一个 auditor，审计链统一。
        self.orchestrator.auditor = self.auditor
        # 用户管理服务依赖 auth，延迟构造
        if self.user_admin is None:
            self.user_admin = UserAdminService(self.auth)
        if self.sessions is None:
            from .session_store import build_session_store
            self.sessions = build_session_store()
        if self.models is None:
            from .model_service import ModelService
            self.models = ModelService()
        if self.files is None:
            from .file_service import FileService
            self.files = FileService()
        if self.voice is None:
            from .voice_service import VoiceService
            self.voice = VoiceService()

    def get_agent(self, agent_id: Optional[str]) -> Dict[str, Any]:
        """供 chat_service 读取智能体业务配置（name/domain/scope/tier）。"""
        return self.agent_service.get(agent_id) or self.agent_service.get("general")

    @property
    def agents(self) -> Dict[str, Dict[str, Any]]:
        """向后兼容：暴露智能体字典。"""
        return self.agent_service._agents
