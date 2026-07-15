"""platform_storage.interfaces — 三类存储的统一接口(为集团设计,实现先做小公司)。

① 关系型:沿用 org_core 的 Repos(SQLite主/PG可换,SQL方言中立)——不在此重复定义。
② 向量 VectorStore:add/search(带 filters)/delete/count —— 本地SQLite落盘 或 Qdrant。
③ 对象 BlobStore:put/get/delete/list —— 本地磁盘 或 MinIO/S3。
所有数据带 tenant_id;search 从第一天就带 filters(集团换 Qdrant 时下推 payload filter)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class VectorHit:
    id: str
    score: float
    payload: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class VectorStore(Protocol):
    def add(self, id: str, vector: List[float], payload: Dict[str, Any]) -> None: ...
    def search(self, vector: List[float], k: int = 5,
               filters: Optional[Dict[str, Any]] = None) -> List[VectorHit]: ...
    def delete(self, ids: Optional[List[str]] = None,
               filters: Optional[Dict[str, Any]] = None) -> int: ...
    def count(self, filters: Optional[Dict[str, Any]] = None) -> int: ...


@runtime_checkable
class BlobStore(Protocol):
    def put(self, tenant_id: str, key: str, data: bytes) -> str: ...   # 返回可取回的定位串
    def get(self, tenant_id: str, key: str) -> bytes: ...
    def delete(self, tenant_id: str, key: str) -> bool: ...
    def list(self, tenant_id: str, prefix: str = "") -> List[str]: ...
