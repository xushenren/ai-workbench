"""backend.adapters.chroma_store — 真实向量库（Chroma）。

⚠️ 未在沙箱测试：需 chromadb + embedding。接口与 secureguard.InMemoryVectorStore 一致
（add / search → List[Doc]），工厂里 swap 是配置级。chromadb 懒加载。
"""
from __future__ import annotations

from typing import List, Optional

from secureguard import Doc


class ChromaVectorStore:
    """Chroma 向量库。InMemoryVectorStore 的真实替身。

    embedding_fn：可传自定义 embedding（如本地 bge 模型）；不传则用 Chroma 默认。
    隔离：建议每个知识库一个 collection，或在 metadata 里带 kb_id 并在 where 过滤。
    """

    def __init__(self, host: str, port: int = 8000, collection: str = "default",
                 embedding_fn: Optional[object] = None) -> None:
        try:
            import chromadb  # 懒加载
        except Exception as e:  # pragma: no cover
            raise RuntimeError("ChromaVectorStore 需要 chromadb：pip install chromadb") from e
        self._client = chromadb.HttpClient(host=host, port=port)
        self._col = self._client.get_or_create_collection(
            name=collection, embedding_function=embedding_fn,
        )

    def add(self, doc: Doc) -> None:  # pragma: no cover - 需真实服务
        self._col.add(ids=[doc.id], documents=[doc.content], metadatas=[doc.metadata or {}])

    def search(self, query: str, k: int = 5) -> List[Doc]:  # pragma: no cover
        res = self._col.query(query_texts=[query], n_results=k)
        docs: List[Doc] = []
        ids = (res.get("ids") or [[]])[0]
        contents = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for i, did in enumerate(ids):
            meta = dict(metas[i]) if i < len(metas) and metas[i] else {}
            if i < len(dists):
                meta["score"] = 1.0 - float(dists[i])  # 距离转相似度（近似）
            docs.append(Doc(did, contents[i] if i < len(contents) else "", meta))
        return docs
