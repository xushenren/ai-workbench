"""platform_storage.config — STORAGE_PROFILE 切换 local|cluster,给业务统一工厂。"""
from __future__ import annotations
import os
from .local_vector_store import LocalVectorStore
from .local_blob_store import LocalBlobStore

def data_dir() -> str:
    return os.getenv("DATA_DIR", "./data")

def profile() -> str:
    return os.getenv("STORAGE_PROFILE", "local").lower()

def make_vector_store():
    if profile() == "cluster":
        # 集团:待接 QdrantStore(龙虾备好 QDRANT_URL 后接);现降级本地,避免启动失败
        try:
            from .qdrant_store import QdrantStore  # 未来实现
            return QdrantStore(os.getenv("QDRANT_URL"), os.getenv("QDRANT_API_KEY"))
        except Exception:
            pass
    return LocalVectorStore(os.path.join(data_dir(), "vectors.db"))

def make_blob_store():
    if profile() == "cluster":
        try:
            from .s3_blob_store import S3BlobStore  # 未来实现
            return S3BlobStore()
        except Exception:
            pass
    return LocalBlobStore(os.path.join(data_dir(), "blobs"))
