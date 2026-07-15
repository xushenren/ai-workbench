"""
kb_core.repository / sqlite — 知识库存储(接口 + SQLite 实现)。
同 org_core:接口与实现分离,小公司 SQLite,大公司换 PG,服务层不变。
"""
from __future__ import annotations

import json
import sqlite3
from typing import Optional, Protocol

from .models import EntryStatus, KBEntry, Pool


class KBRepo(Protocol):
    def add(self, e: KBEntry) -> None: ...
    def get(self, tenant_id: str, entry_id: str) -> Optional[KBEntry]: ...
    def update(self, e: KBEntry) -> None: ...
    def by_pool(self, tenant_id: str, pool: Pool) -> list[KBEntry]: ...
    def all_active(self, tenant_id: str) -> list[KBEntry]: ...


SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_entries (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, pool TEXT NOT NULL,
  owner_user_id TEXT NOT NULL, owner_grant_id TEXT NOT NULL, org_node_id TEXT NOT NULL,
  title TEXT, content TEXT, claims TEXT, shared INTEGER, external_ok INTEGER,
  source TEXT, status TEXT NOT NULL, ai_verdict TEXT, promoted_by TEXT, created_at REAL
);
CREATE INDEX IF NOT EXISTS ix_kb_pool ON kb_entries(tenant_id, pool, status);
CREATE INDEX IF NOT EXISTS ix_kb_owner ON kb_entries(tenant_id, owner_user_id);
"""


class SqliteKBRepo:
    def __init__(self, path: str = ":memory:") -> None:
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    def _row(self, r: sqlite3.Row) -> KBEntry:
        return KBEntry(
            id=r["id"], tenant_id=r["tenant_id"], pool=Pool(r["pool"]),
            owner_user_id=r["owner_user_id"], owner_grant_id=r["owner_grant_id"],
            org_node_id=r["org_node_id"], title=r["title"] or "", content=r["content"] or "",
            claims=json.loads(r["claims"] or "{}"), shared=bool(r["shared"]),
            external_ok=bool(r["external_ok"]), source=r["source"] or "",
            status=EntryStatus(r["status"]), ai_verdict=r["ai_verdict"] or "",
            promoted_by=r["promoted_by"], created_at=r["created_at"] or 0.0,
        )

    def add(self, e: KBEntry) -> None:
        self.db.execute(
            "INSERT INTO kb_entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (e.id, e.tenant_id, e.pool.value, e.owner_user_id, e.owner_grant_id, e.org_node_id,
             e.title, e.content, json.dumps(e.claims, ensure_ascii=False), int(e.shared),
             int(e.external_ok), e.source, e.status.value, e.ai_verdict, e.promoted_by, e.created_at))
        self.db.commit()

    def get(self, tenant_id: str, entry_id: str) -> Optional[KBEntry]:
        r = self.db.execute("SELECT * FROM kb_entries WHERE tenant_id=? AND id=?", (tenant_id, entry_id)).fetchone()
        return self._row(r) if r else None

    def update(self, e: KBEntry) -> None:
        self.db.execute(
            "UPDATE kb_entries SET pool=?, shared=?, external_ok=?, status=?, ai_verdict=?, promoted_by=? "
            "WHERE tenant_id=? AND id=?",
            (e.pool.value, int(e.shared), int(e.external_ok), e.status.value, e.ai_verdict, e.promoted_by,
             e.tenant_id, e.id))
        self.db.commit()

    def by_pool(self, tenant_id: str, pool: Pool) -> list[KBEntry]:
        rows = self.db.execute(
            "SELECT * FROM kb_entries WHERE tenant_id=? AND pool=? AND status='active'", (tenant_id, pool.value)).fetchall()
        return [self._row(r) for r in rows]

    def all_active(self, tenant_id: str) -> list[KBEntry]:
        rows = self.db.execute("SELECT * FROM kb_entries WHERE tenant_id=? AND status='active'", (tenant_id,)).fetchall()
        return [self._row(r) for r in rows]
