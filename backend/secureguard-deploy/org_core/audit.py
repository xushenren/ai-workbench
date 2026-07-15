"""
org_core.audit — 审计哈希链(全局可见、不可篡改、锚定真人+子账号)。

每条审计的 hash = sha256(prev_hash + 关键字段),链式串联:改任一条,后续全对不上。
审计是底座能力,永远开,不进可配项。
"""
from __future__ import annotations

import hashlib
import uuid

from .models import AuditEntry
from .repository import Repos


def _digest(prev: str, e: AuditEntry) -> str:
    raw = f"{prev}|{e.tenant_id}|{e.user_id}|{e.grant_id}|{e.action}|{e.target}|{e.ok}|{e.ts}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def write_audit(repo: Repos, *, tenant_id: str, user_id: str, grant_id: str | None,
                action: str, target: str, ok: bool, reason: str = "") -> AuditEntry:
    prev = repo.last_audit_hash(tenant_id)
    e = AuditEntry(
        id=uuid.uuid4().hex, tenant_id=tenant_id, user_id=user_id, grant_id=grant_id,
        action=action, target=target, ok=ok, reason=reason, prev_hash=prev,
    )
    e.hash = _digest(prev, e)
    repo.append_audit(e)
    return e


def verify_chain(repo: Repos, tenant_id: str) -> bool:
    """校验审计链完整性(逆序拉取后正序验证)。"""
    entries = list(reversed(repo.list_audit(tenant_id, limit=10_000)))
    prev = ""
    for e in entries:
        if e.prev_hash != prev or e.hash != _digest(prev, e):
            return False
        prev = e.hash
    return True
