"""backend.adapters — 真实后端适配器（B7）。全部 import-guarded，无依赖时类仍可导入。"""
from .vllm_model import VLLMModel
from .chroma_store import ChromaVectorStore
from .redis_quota import RedisQuotaService

__all__ = ["VLLMModel", "ChromaVectorStore", "RedisQuotaService"]
