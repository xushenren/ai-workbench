"""platform_storage.local_vector_store — 本地 SQLite 落盘向量库(替换重启即丢的内存版)。

- 向量 + payload(tenant_id/kb_id/doc_id/content/pool 等)落盘,重启不丢、可随 DATA_DIR 搬迁。
- search 带 filters(tenant_id 精确、kb_id 列表 IN、pool 精确、其余等值),余弦相似度在 Python 计算。
- 接口与 Qdrant 版一致(集团切 Qdrant 时 filters 下推为 payload filter),调用方零改动。
小规模足够;超大规模换 QdrantStore。纯 stdlib + sqlite3。
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from .interfaces import VectorHit

_RESERVED = {"tenant_id", "kb_id", "doc_id", "pool"}   # 建索引列;其余 payload 存 JSON


class LocalVectorStore:
    def __init__(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS vectors (
                id TEXT PRIMARY KEY,
                tenant_id TEXT, kb_id TEXT, doc_id TEXT, pool TEXT,
                content TEXT, payload TEXT, vector TEXT
            )""")
        self.db.execute("CREATE INDEX IF NOT EXISTS ix_vec_scope ON vectors(tenant_id, kb_id)")
        self.db.commit()

    def add(self, id: str, vector: List[float], payload: Dict[str, Any]) -> None:
        with self._lock:
            self.db.execute(
                "INSERT OR REPLACE INTO vectors(id,tenant_id,kb_id,doc_id,pool,content,payload,vector)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (id, payload.get("tenant_id"), payload.get("kb_id"), payload.get("doc_id"),
                 payload.get("pool"), payload.get("content", ""),
                 json.dumps(payload, ensure_ascii=False), json.dumps(vector)))
            self.db.commit()

    def _where(self, filters: Optional[Dict[str, Any]]):
        if not filters:
            return "", []
        clauses, params = [], []
        for kdb in ("tenant_id", "doc_id", "pool"):
            if kdb in filters and filters[kdb] is not None:
                clauses.append(f"{kdb}=?"); params.append(filters[kdb])
        if "kb_id" in filters and filters["kb_id"] is not None:
            v = filters["kb_id"]
            if isinstance(v, (list, tuple, set)):
                v = list(v)
                if not v:
                    return "WHERE 1=0", []          # 空列表=不匹配任何
                clauses.append(f"kb_id IN ({','.join('?'*len(v))})"); params.extend(v)
            else:
                clauses.append("kb_id=?"); params.append(v)
        return ("WHERE " + " AND ".join(clauses)) if clauses else "", params

    def search(self, vector: List[float], k: int = 5,
               filters: Optional[Dict[str, Any]] = None) -> List[VectorHit]:
        where, params = self._where(filters)
        rows = self.db.execute(f"SELECT id,payload,vector FROM vectors {where}", params).fetchall()
        qn = math.sqrt(sum(x * x for x in vector)) or 1e-9
        scored = []
        for r in rows:
            v = json.loads(r["vector"])
            if len(v) != len(vector):
                continue
            dot = sum(a * b for a, b in zip(vector, v))
            vn = math.sqrt(sum(x * x for x in v)) or 1e-9
            scored.append(VectorHit(r["id"], dot / (qn * vn), json.loads(r["payload"])))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:k]

    def delete(self, ids: Optional[List[str]] = None,
               filters: Optional[Dict[str, Any]] = None) -> int:
        with self._lock:
            if ids:
                cur = self.db.execute(
                    f"DELETE FROM vectors WHERE id IN ({','.join('?'*len(ids))})", list(ids))
            else:
                where, params = self._where(filters)
                cur = self.db.execute(f"DELETE FROM vectors {where}", params)
            self.db.commit()
            return cur.rowcount

    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        where, params = self._where(filters)
        return self.db.execute(f"SELECT COUNT(*) c FROM vectors {where}", params).fetchone()["c"]
