"""platform_storage.local_blob_store — 本地磁盘对象存储(接口同 S3/MinIO 版)。"""
from __future__ import annotations
import os, re
from typing import List

_SAFE = re.compile(r"[^A-Za-z0-9_.\-/]")

class LocalBlobStore:
    def __init__(self, root: str) -> None:
        self.root = root
        os.makedirs(root, exist_ok=True)

    def _path(self, tenant_id: str, key: str) -> str:
        t = _SAFE.sub("_", tenant_id or "default")
        k = _SAFE.sub("_", key).lstrip("/")
        p = os.path.normpath(os.path.join(self.root, t, k))
        if not p.startswith(os.path.normpath(os.path.join(self.root, t))):
            raise ValueError("非法 key(路径穿越)")
        return p

    def put(self, tenant_id: str, key: str, data: bytes) -> str:
        p = self._path(tenant_id, key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        return f"local://{tenant_id}/{key}"

    def get(self, tenant_id: str, key: str) -> bytes:
        with open(self._path(tenant_id, key), "rb") as f:
            return f.read()

    def delete(self, tenant_id: str, key: str) -> bool:
        p = self._path(tenant_id, key)
        if os.path.exists(p):
            os.remove(p); return True
        return False

    def list(self, tenant_id: str, prefix: str = "") -> List[str]:
        base = os.path.join(self.root, _SAFE.sub("_", tenant_id or "default"))
        out = []
        for root, _, files in os.walk(base):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), base)
                if rel.startswith(prefix):
                    out.append(rel)
        return sorted(out)
