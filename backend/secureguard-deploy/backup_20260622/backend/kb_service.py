"""backend.kb_service — 知识库与检索隔离（B5，框架无关核心）。

D7 隔离铁律：检索范围 = 公共库 + 本部门库 + 自己私有库，**绝不可达他人私有库**。
隔离**下推到检索**——先用 permissions.can_access_kb 算出可达库集合，只在这些库里搜，
而不是"先搜全部再过滤"（后者一旦逻辑漏一处就越权）。

每个库一个独立的内存向量库（离线可测）。真实分段+向量化(embedding+Chroma)是 🔴 入库路径，
给出接口与桩，标注需真机。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from secureguard import InMemoryVectorStore, Doc
from secureguard.permissions import (
    User, KnowledgeBase, Visibility, can_access_kb, can_read_kb_content, can_audit_read_kb,
)

# 匿名用户：只可达公共库
from secureguard.permissions import Role
_ANON = User(id="__anon__", role=Role.USER, dept_id=None)


class KBService:
    """知识库存储 + 隔离检索。生产把向量库换 Chroma（B7），隔离逻辑不变。"""

    def __init__(self, seed: bool = True) -> None:
        self._kbs: Dict[str, Dict[str, Any]] = {}
        self._stores: Dict[str, InMemoryVectorStore] = {}
        if seed:
            self._seed()

    @staticmethod
    def _view(rec: Dict[str, Any]) -> KnowledgeBase:
        return KnowledgeBase(id=rec["id"], visibility=Visibility(rec["visibility"]),
                             owner_id=rec.get("owner_id"), dept_id=rec.get("dept_id"))

    # ---------- 列表（隔离过滤） ----------
    def list_for(self, caller: Optional[User]) -> List[Dict[str, Any]]:
        user = caller or _ANON
        return [
            {"id": r["id"], "name": r["name"], "type": r["visibility"], "doc_count": r["doc_count"]}
            for r in self._kbs.values()
            if can_access_kb(user, self._view(r))[0]
        ]

    def accessible_ids(self, caller: Optional[User]) -> List[str]:
        user = caller or _ANON
        return [r["id"] for r in self._kbs.values() if can_access_kb(user, self._view(r))[0]]

    # ---------- 隔离检索 ----------
    def search(self, caller: Optional[User], query: str, k: int = 5) -> Dict[str, Any]:
        """只在调用者可达的库里检索。结果带来源库，便于溯源高亮。"""
        ids = self.accessible_ids(caller)
        hits: List[Dict[str, Any]] = []
        for kb_id in ids:
            store = self._stores.get(kb_id)
            if not store:
                continue
            for doc in store.search(query, k):
                hits.append({
                    "kb_id": kb_id, "kb_name": self._kbs[kb_id]["name"],
                    "doc_id": doc.id, "content": doc.content,
                    "score": float(doc.metadata.get("score", doc.metadata.get("trust_score", 0.5))),
                })
        hits.sort(key=lambda h: h["score"], reverse=True)
        return {"query": query, "accessible_kbs": ids, "results": hits[:k]}

    # ---------- 入库 ----------
    def ingest_text(self, caller: User, kb_id: str, doc_id: str, text: str) -> Dict[str, Any]:
        """把一段文本加入某库（内存向量库，离线可测）。

        真实生产：先分段、过 embedding 模型、写 Chroma —— 那部分是 🔴，需真机。
        这里走内存库，验证的是"隔离+检索"链路，不是真实向量化质量。
        """
        rec = self._kbs.get(kb_id)
        if not rec:
            raise KeyError(f"知识库不存在: {kb_id}")
        # 只有能管理该库者可写（私有库仅 owner；部门库部门管理员；公共库 admin）
        if not can_read_kb_content(caller, self._view(rec))[0] and caller.id != rec.get("owner_id"):
            from secureguard.permissions import PermissionDenied
            raise PermissionDenied("无权写入该知识库")
        self._stores[kb_id].add(Doc(doc_id, text, {"kb_id": kb_id}))
        rec["doc_count"] += 1
        return {"kb_id": kb_id, "doc_count": rec["doc_count"]}

    # ---------- 受控审计读取（仅 auditor；必留痕） ----------
    def audit_list_all(self, caller: User) -> List[Dict[str, Any]]:
        """审计员列出**全部**知识库（含他人私有）的元数据——不含内容。"""
        if caller.role.value != "auditor":
            from secureguard.permissions import PermissionDenied
            raise PermissionDenied("仅审计员可列出全部知识库")
        return [
            {"id": r["id"], "name": r["name"], "type": r["visibility"],
             "owner_id": r.get("owner_id"), "dept_id": r.get("dept_id"), "doc_count": r["doc_count"]}
            for r in self._kbs.values()
        ]

    def audit_read(self, caller: User, kb_id: str, reason: str, auditor_log: Any) -> Dict[str, Any]:
        """审计员读取某库原文。**强制 reason + 写哈希链审计**（受控、可问责、不可篡改）。

        与日常 can_read_kb_content 分离：这是唯一能让非 owner 看到私有库原文的通道，
        且每次都在审计链留下"谁、何时、看了谁的哪个库、为什么"。
        """
        rec = self._kbs.get(kb_id)
        if not rec:
            raise KeyError(f"知识库不存在: {kb_id}")
        ok, why = can_audit_read_kb(caller, self._view(rec))
        if not ok:
            from secureguard.permissions import PermissionDenied
            raise PermissionDenied(why)
        if not reason or not reason.strip():
            raise ValueError("审计读取必须提供理由（reason）")
        # 写入哈希链审计——这条记录本身不可篡改，可被更高层复核
        auditor_log.log_stage(
            stage="AUDIT_READ", decision="ACCESS", session_id=caller.id,
            reason=reason.strip(),
            extra={"kb_id": kb_id, "kb_owner": rec.get("owner_id"),
                   "kb_visibility": rec["visibility"], "auditor": caller.id},
        )
        return {"kb_id": kb_id, "kb_name": rec["name"], "owner_id": rec.get("owner_id"),
                "reason": reason.strip(), "documents": self._all_docs(kb_id), "audited": True}

    def _all_docs(self, kb_id: str) -> List[Dict[str, str]]:
        """取某库全部文档原文（审计用）。InMemoryVectorStore 内部以 _docs 存 Doc。"""
        store = self._stores.get(kb_id)
        if store is None:
            return []
        return [{"doc_id": d.id, "content": d.content} for d in getattr(store, "_docs", [])]

    # ---------- 种子 ----------
    def _seed(self) -> None:
        defs = [
            {"id": "kb_std", "name": "标准库附录", "visibility": "public", "owner_id": "u_admin",
             "dept_id": None, "docs": [("std_1", "风管安装验收应符合 GB50243，漏风率需达标。"),
                                        ("std_2", "GB50303 规定电气装置安装的接地与绝缘要求。")]},
            {"id": "kb_dept", "name": "施工方案库", "visibility": "department", "owner_id": "u_da",
             "dept_id": "d1", "docs": [("plan_1", "某项目暖通施工方案：风管路由与支吊架间距。")]},
            {"id": "kb_user1", "name": "我的笔记", "visibility": "private", "owner_id": "u1",
             "dept_id": "d1", "docs": [("note_1", "个人笔记：现场验收检查清单与注意事项。")]},
            {"id": "kb_user2", "name": "他人笔记", "visibility": "private", "owner_id": "u2",
             "dept_id": "d2", "docs": [("note_2", "u2 的私有内容，u1 不应检索到。")]},
        ]
        for d in defs:
            self._kbs[d["id"]] = {
                "id": d["id"], "name": d["name"], "visibility": d["visibility"],
                "owner_id": d["owner_id"], "dept_id": d["dept_id"], "doc_count": len(d["docs"]),
            }
            store = InMemoryVectorStore()
            for did, text in d["docs"]:
                store.add(Doc(did, text, {"kb_id": d["id"], "trust_score": 0.8}))
            self._stores[d["id"]] = store
