"""platform_storage.persistent_kb_adapter — 让 kb_service 零改动用上落盘向量库。

完全模拟老 InMemoryVectorStore 的接口:
    add(doc)              # doc: 具 .id/.content/.metadata
    search(query, k=5)    # 文本查询 → 返回 List[Doc](含 .id/.content/.metadata,metadata里带score)
    ._docs                # 审计用:返回 List[Doc]
落盘到 LocalVectorStore(SQLite),重启不丢、随 DATA_DIR 搬迁。

检索双模式:
  - 默认(无嵌入函数):落盘 + 关键词打分(行为兼容老版,零依赖,立即根治"重启即丢")。
  - 注入 embed_fn(text)->List[float] 后:自动升级为向量语义检索(落盘同一份数据)。
kb_service 只需把 `InMemoryVectorStore()` 换成 `PersistentVectorStore(path=..., tenant_id=..)`。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .local_vector_store import LocalVectorStore


@dataclass
class Doc:
    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# 关键词模式的"伪向量":把文本散列成固定维稀疏向量,让 LocalVectorStore 也能存/搜;
# 但默认检索走关键词打分(下方 _keyword_search),保证与老版行为一致。
def _tokenize(text: str) -> List[str]:
    # 中英混合:英文按词,中文按字(简易,够关键词匹配)
    text = text.lower()
    en = re.findall(r"[a-z0-9]+", text)
    zh = re.findall(r"[\u4e00-\u9fff]", text)
    return en + zh


class PersistentVectorStore:
    def __init__(self, path: str, tenant_id: str = "t_default",
                 embed_fn: Optional[Callable[[str], List[float]]] = None,
                 default_pool: str = "") -> None:
        self.vs = LocalVectorStore(path)
        self.tenant_id = tenant_id
        self.embed_fn = embed_fn
        self.default_pool = default_pool

    # ---- 与老接口一致 ----
    def add(self, doc: "Any") -> None:
        content = getattr(doc, "content", "")
        meta = dict(getattr(doc, "metadata", {}) or {})
        payload = {
            "tenant_id": meta.get("tenant_id", self.tenant_id),
            "kb_id": meta.get("kb_id"),
            "doc_id": getattr(doc, "id", None),
            "pool": meta.get("pool", self.default_pool),
            "content": content,
            "meta": meta,                       # 保留原始 metadata(含 trust_score 等)
        }
        vec = self.embed_fn(content) if self.embed_fn else _stub_vector(content)
        self.vs.add(str(getattr(doc, "id", "")), vec, payload)

    def search(self, query: str, k: int = 5, kb_ids: Optional[List[str]] = None) -> List["Doc"]:
        filters: Dict[str, Any] = {"tenant_id": self.tenant_id}
        if kb_ids:
            filters["kb_id"] = list(kb_ids)
        if self.embed_fn:
            hits = self.vs.search(self.embed_fn(query), k, filters)      # 语义
        else:
            hits = self._keyword_search(query, k, filters)              # 关键词(默认)
        out = []
        for h in hits:
            p = h.payload
            meta = dict(p.get("meta") or {})
            meta["score"] = round(h.score, 4)
            out.append(Doc(id=p.get("doc_id") or h.id, content=p.get("content", ""), metadata=meta))
        return out

    @property
    def _docs(self) -> List["Doc"]:
        """审计:返回全部文档(List[Doc])。"""
        rows = self.vs.db.execute(
            "SELECT id,doc_id,content,payload FROM vectors WHERE tenant_id=?",
            (self.tenant_id,)).fetchall()
        import json
        res = []
        for r in rows:
            meta = (json.loads(r["payload"]).get("meta")) or {}
            res.append(Doc(id=r["doc_id"] or r["id"], content=r["content"], metadata=meta))
        return res

    # ---- 关键词检索(默认,行为兼容老内存版)----
    def _keyword_search(self, query: str, k: int, filters: Dict[str, Any]):
        from .interfaces import VectorHit
        where, params = self.vs._where(filters)
        rows = self.vs.db.execute(f"SELECT id,payload,content FROM vectors {where}", params).fetchall()
        import json
        qtok = set(_tokenize(query))
        scored = []
        for r in rows:
            ctok = _tokenize(r["content"])
            if not ctok:
                continue
            overlap = sum(1 for t in ctok if t in qtok)
            score = overlap / (len(qtok) or 1)
            if score > 0:
                scored.append(VectorHit(r["id"], score, json.loads(r["payload"])))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:k]


def _stub_vector(text: str, dim: int = 64) -> List[float]:
    """无嵌入模型时的占位向量(哈希词袋);仅为落盘,检索用关键词。"""
    v = [0.0] * dim
    for t in _tokenize(text):
        v[hash(t) % dim] += 1.0
    return v
