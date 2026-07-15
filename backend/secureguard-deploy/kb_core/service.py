"""
kb_core.service — 三池知识库的操作入口(复用 org_core 鉴权 + 审计)。

落地前几轮定稿的设计:
  普通用户上传 → 私有池(同意共享→公有低置信池)
  专家(can_promote_kb)上传 → AI 体检 → 专家拍板(可推翻AI,留痕)→ 公有高置信池
  检索按"当前子账号身份"过滤可见知识;匿名只见 external_ok 的高置信。
  全程审计 + 可回滚(后悔药,非审批环节)。
"""
from __future__ import annotations

import uuid
from typing import Optional

from org_core import P, authorize, write_audit
from org_core.authz import resolve_grant

from .inspect import ModelInspector, inspect
from .models import EntryStatus, Inspection, KBEntry, Pool
from .repository import KBRepo


class KBConflict(Exception):
    """AI 体检发现与高置信池冲突,专家未明确推翻 → 阻断,需 decision_override=True 拍板。"""
    def __init__(self, inspection: Inspection) -> None:
        super().__init__("AI 体检发现冲突,需专家拍板推翻")
        self.inspection = inspection


class KBService:
    def __init__(self, org_repo, kb_repo: KBRepo, model_inspector: ModelInspector = None) -> None:
        self.org = org_repo                 # org_core 的 Repos(鉴权/审计)
        self.kb = kb_repo
        self.model_inspector = model_inspector

    # ------------------------------------------------------------------ #
    # 普通上传:私有 / (同意共享)公有低置信
    # ------------------------------------------------------------------ #
    def upload(self, tenant_id: str, grant_id: str, *, title: str, content: str,
               claims: Optional[dict] = None, share: bool = False, source: str = "") -> KBEntry:
        g = resolve_grant(self.org, tenant_id, grant_id)
        ok, reason = authorize(self.org, tenant_id, grant_id, P.KB_WRITE_PRIVATE, g.org_node_id)
        write_audit(self.org, tenant_id=tenant_id, user_id=g.user_id, grant_id=grant_id,
                    action="kb.upload", target=title, ok=ok, reason=reason)
        if not ok:
            raise PermissionError(reason)
        pool = Pool.PUBLIC_LOW if share else Pool.PRIVATE
        e = KBEntry(uuid.uuid4().hex, tenant_id, pool, g.user_id, grant_id, g.org_node_id,
                    title, content, claims or {}, shared=share, source=source)
        self.kb.add(e)
        return e

    def consent_share(self, tenant_id: str, grant_id: str, entry_id: str) -> KBEntry:
        """owner 把自己的私有条目改为同意共享 → 进公有低置信池。"""
        g = resolve_grant(self.org, tenant_id, grant_id)
        e = self.kb.get(tenant_id, entry_id)
        if not e or e.owner_user_id != g.user_id:
            raise PermissionError("只能共享自己的条目")
        e.shared = True
        e.pool = Pool.PUBLIC_LOW
        self.kb.update(e)
        write_audit(self.org, tenant_id=tenant_id, user_id=g.user_id, grant_id=grant_id,
                    action="kb.share", target=entry_id, ok=True, reason="同意共享→低置信")
        return e

    # ------------------------------------------------------------------ #
    # 专家晋升:AI 体检 → 拍板 → 高置信
    # ------------------------------------------------------------------ #
    def inspect_candidate(self, tenant_id: str, draft: KBEntry) -> Inspection:
        return inspect(self.kb, draft, self.model_inspector)

    def promote_to_high(self, tenant_id: str, grant_id: str, *, title: str, content: str,
                        claims: Optional[dict] = None, external_ok: bool = False,
                        source: str = "", decision_override: bool = False) -> tuple[KBEntry, Inspection]:
        """专家把知识晋升进公有高置信。需 can_promote_kb。
        AI 体检报冲突且未拍板推翻 → 抛 KBConflict(不入库)。"""
        g = resolve_grant(self.org, tenant_id, grant_id)
        ok, reason = authorize(self.org, tenant_id, grant_id, P.KB_PROMOTE, g.org_node_id)
        if not ok:
            write_audit(self.org, tenant_id=tenant_id, user_id=g.user_id, grant_id=grant_id,
                        action="kb.promote", target=title, ok=False, reason=reason)
            raise PermissionError(reason)

        draft = KBEntry(uuid.uuid4().hex, tenant_id, Pool.PUBLIC_HIGH, g.user_id, grant_id,
                        g.org_node_id, title, content, claims or {}, shared=True,
                        external_ok=external_ok, source=source)
        report = self.inspect_candidate(tenant_id, draft)

        if report.has_conflict and not decision_override:
            write_audit(self.org, tenant_id=tenant_id, user_id=g.user_id, grant_id=grant_id,
                        action="kb.promote", target=title, ok=False,
                        reason=f"AI体检冲突待拍板: {report.conflicts}")
            raise KBConflict(report)

        # 入库:记录 AI 结论 + 是否专家推翻
        draft.ai_verdict = report.confidence_advice + (" | 专家推翻AI" if (report.has_conflict and decision_override) else "")
        draft.promoted_by = g.user_id
        self.kb.add(draft)
        write_audit(self.org, tenant_id=tenant_id, user_id=g.user_id, grant_id=grant_id,
                    action="kb.promote", target=draft.id, ok=True,
                    reason=("专家推翻AI入库" if (report.has_conflict and decision_override) else "入库高置信"))
        return draft, report

    def rollback(self, tenant_id: str, grant_id: str, entry_id: str) -> None:
        """晋升后悔药:把高置信条目退回作废。需 can_promote_kb。"""
        g = resolve_grant(self.org, tenant_id, grant_id)
        ok, reason = authorize(self.org, tenant_id, grant_id, P.KB_PROMOTE, g.org_node_id)
        if not ok:
            raise PermissionError(reason)
        e = self.kb.get(tenant_id, entry_id)
        if not e:
            raise KeyError("条目不存在")
        e.status = EntryStatus.ROLLED_BACK
        self.kb.update(e)
        write_audit(self.org, tenant_id=tenant_id, user_id=g.user_id, grant_id=grant_id,
                    action="kb.rollback", target=entry_id, ok=True, reason="高置信回滚")

    # ------------------------------------------------------------------ #
    # 检索:按身份过滤(命门)
    # ------------------------------------------------------------------ #
    def retrieve(self, tenant_id: str, current_grant_id: Optional[str], query: str) -> list[KBEntry]:
        """current_grant_id=None 表示匿名/外部。返回可见且匹配的条目(带 pool=置信标签)。"""
        entries = self.kb.all_active(tenant_id)
        q = query.strip()

        if current_grant_id is None:
            # 匿名/外部:只见 对外可公开 的高置信
            visible = [e for e in entries if e.pool == Pool.PUBLIC_HIGH and e.external_ok]
        else:
            try:
                g = resolve_grant(self.org, tenant_id, current_grant_id)
            except (LookupError, PermissionError):
                return []
            ok, _ = authorize(self.org, tenant_id, current_grant_id, P.KB_READ, g.org_node_id)
            if not ok:
                return []
            # 已登录:本人私有 + 全部公有(低/高);"在 A 看不到 B" 对私有自动成立(按 owner)
            visible = [
                e for e in entries
                if e.pool in (Pool.PUBLIC_LOW, Pool.PUBLIC_HIGH)
                or (e.pool == Pool.PRIVATE and e.owner_user_id == g.user_id)
            ]
        # 朴素匹配(生产换向量检索)
        return [e for e in visible if not q or q in e.title or q in e.content or q in " ".join(e.claims.values())]
