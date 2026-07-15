"""backend — 企业 AI 工作台业务后端（包装 SecureGuard 内核）。"""
from .state import AppState
from .chat_service import run_chat, collect_answer, scope_check

__all__ = ["AppState", "run_chat", "collect_answer", "scope_check"]
