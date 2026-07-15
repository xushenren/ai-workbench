"""
org_core.sqlite_repo — Repos 的 SQLite 实现(小公司单机形态)。

纯 stdlib sqlite3。Schema 含全部七表 + tenant_id + 外键 + 索引,结构兼容 Postgres
(换 PostgresRepos 时同一套表只改方言)。大公司用 PG 实现,业务代码不变。
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from .models import (
    AdminScope, AuditEntry, Grant, NodeType, OrgNode, Role, Tenant, User,
    UserKind, UserStatus,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
  id TEXT PRIMARY KEY, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS org_nodes (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, parent_id TEXT,
  type TEXT NOT NULL, name TEXT NOT NULL,
  FOREIGN KEY(tenant_id) REFERENCES tenants(id)
);
CREATE INDEX IF NOT EXISTS ix_org_tenant ON org_nodes(tenant_id, parent_id);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, kind TEXT NOT NULL,
  status TEXT NOT NULL, display_name TEXT,
  FOREIGN KEY(tenant_id) REFERENCES tenants(id)
);
CREATE INDEX IF NOT EXISTS ix_users_tenant ON users(tenant_id);
CREATE TABLE IF NOT EXISTS roles (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL,
  perm_keys TEXT NOT NULL,
  FOREIGN KEY(tenant_id) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS grants (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, user_id TEXT NOT NULL,
  role_id TEXT NOT NULL, org_node_id TEXT NOT NULL, label TEXT,
  active INTEGER NOT NULL DEFAULT 1, is_default INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(tenant_id) REFERENCES tenants(id)
);
CREATE INDEX IF NOT EXISTS ix_grants_user ON grants(tenant_id, user_id);
CREATE TABLE IF NOT EXISTS admin_scopes (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, user_id TEXT NOT NULL,
  org_node_id TEXT NOT NULL,
  FOREIGN KEY(tenant_id) REFERENCES tenants(id)
);
CREATE INDEX IF NOT EXISTS ix_adminscope_user ON admin_scopes(tenant_id, user_id);
CREATE TABLE IF NOT EXISTS audit_log (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, user_id TEXT NOT NULL,
  grant_id TEXT, action TEXT NOT NULL, target TEXT, ok INTEGER NOT NULL,
  reason TEXT, ts REAL NOT NULL, prev_hash TEXT, hash TEXT NOT NULL,
  FOREIGN KEY(tenant_id) REFERENCES tenants(id)
);
CREATE INDEX IF NOT EXISTS ix_audit_tenant ON audit_log(tenant_id, ts);
"""


class SqliteRepos:
    def __init__(self, path: str = ":memory:") -> None:
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ---- tenant ----
    def add_tenant(self, t: Tenant) -> None:
        self.db.execute("INSERT INTO tenants(id,name) VALUES(?,?)", (t.id, t.name)); self.db.commit()

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        r = self.db.execute("SELECT * FROM tenants WHERE id=?", (tenant_id,)).fetchone()
        return Tenant(r["id"], r["name"]) if r else None

    # ---- org tree ----
    def add_node(self, n: OrgNode) -> None:
        self.db.execute("INSERT INTO org_nodes(id,tenant_id,parent_id,type,name) VALUES(?,?,?,?,?)",
                        (n.id, n.tenant_id, n.parent_id, n.type.value, n.name)); self.db.commit()

    def get_node(self, tenant_id: str, node_id: str) -> Optional[OrgNode]:
        r = self.db.execute("SELECT * FROM org_nodes WHERE tenant_id=? AND id=?", (tenant_id, node_id)).fetchone()
        return OrgNode(r["id"], r["tenant_id"], r["parent_id"], NodeType(r["type"]), r["name"]) if r else None

    def children(self, tenant_id: str, node_id: Optional[str]) -> list[OrgNode]:
        rows = self.db.execute("SELECT * FROM org_nodes WHERE tenant_id=? AND parent_id IS ?",
                               (tenant_id, node_id)).fetchall()
        return [OrgNode(r["id"], r["tenant_id"], r["parent_id"], NodeType(r["type"]), r["name"]) for r in rows]

    def update_node(self, n: OrgNode) -> None:
        self.db.execute("UPDATE org_nodes SET parent_id=?, type=?, name=? WHERE tenant_id=? AND id=?",
                        (n.parent_id, n.type.value, n.name, n.tenant_id, n.id)); self.db.commit()

    # ---- users ----
    def add_user(self, u: User) -> None:
        self.db.execute("INSERT INTO users(id,tenant_id,kind,status,display_name) VALUES(?,?,?,?,?)",
                        (u.id, u.tenant_id, u.kind.value, u.status.value, u.display_name)); self.db.commit()

    def get_user(self, tenant_id: str, user_id: str) -> Optional[User]:
        r = self.db.execute("SELECT * FROM users WHERE tenant_id=? AND id=?", (tenant_id, user_id)).fetchone()
        return User(r["id"], r["tenant_id"], UserKind(r["kind"]), UserStatus(r["status"]), r["display_name"] or "") if r else None

    def set_user_status(self, tenant_id: str, user_id: str, status: str) -> None:
        self.db.execute("UPDATE users SET status=? WHERE tenant_id=? AND id=?", (status, tenant_id, user_id)); self.db.commit()

    # ---- roles ----
    def add_role(self, r: Role) -> None:
        self.db.execute("INSERT INTO roles(id,tenant_id,name,perm_keys) VALUES(?,?,?,?)",
                        (r.id, r.tenant_id, r.name, ",".join(sorted(r.perm_keys)))); self.db.commit()

    def get_role(self, tenant_id: str, role_id: str) -> Optional[Role]:
        r = self.db.execute("SELECT * FROM roles WHERE tenant_id=? AND id=?", (tenant_id, role_id)).fetchone()
        if not r:
            return None
        perms = frozenset(p for p in (r["perm_keys"] or "").split(",") if p)
        return Role(r["id"], r["tenant_id"], r["name"], perms)

    # ---- grants ----
    def add_grant(self, g: Grant) -> None:
        self.db.execute(
            "INSERT INTO grants(id,tenant_id,user_id,role_id,org_node_id,label,active,is_default) VALUES(?,?,?,?,?,?,?,?)",
            (g.id, g.tenant_id, g.user_id, g.role_id, g.org_node_id, g.label, int(g.active), int(g.is_default)))
        self.db.commit()

    def _grant(self, r: sqlite3.Row) -> Grant:
        return Grant(r["id"], r["tenant_id"], r["user_id"], r["role_id"], r["org_node_id"],
                     r["label"] or "", bool(r["active"]), bool(r["is_default"]))

    def get_grant(self, tenant_id: str, grant_id: str) -> Optional[Grant]:
        r = self.db.execute("SELECT * FROM grants WHERE tenant_id=? AND id=?", (tenant_id, grant_id)).fetchone()
        return self._grant(r) if r else None

    def grants_of_user(self, tenant_id: str, user_id: str) -> list[Grant]:
        rows = self.db.execute("SELECT * FROM grants WHERE tenant_id=? AND user_id=?", (tenant_id, user_id)).fetchall()
        return [self._grant(r) for r in rows]

    
    # ---- batch list (for API) ----
    def _list_users(self, tenant_id: str) -> list:
        rows = self.db.execute("SELECT * FROM users WHERE tenant_id=?", (tenant_id,)).fetchall()
        return [User(r["id"], r["tenant_id"], UserKind(r["kind"]), UserStatus(r["status"]), r["display_name"] or "") for r in rows]

    def _list_roles(self, tenant_id: str) -> list:
        rows = self.db.execute("SELECT * FROM roles WHERE tenant_id=?", (tenant_id,)).fetchall()
        return [Role(r["id"], r["tenant_id"], r["name"], frozenset(r["perm_keys"].split(";") if r["perm_keys"] else [])) for r in rows]

    def _list_grants(self, tenant_id: str) -> list:
        rows = self.db.execute("SELECT * FROM grants WHERE tenant_id=? AND active=1", (tenant_id,)).fetchall()
        return [self._grant(r) for r in rows]

    def set_grant_active(self, tenant_id: str, grant_id: str, active: bool) -> None:
        self.db.execute("UPDATE grants SET active=? WHERE tenant_id=? AND id=?", (int(active), tenant_id, grant_id)); self.db.commit()

    # ---- admin scopes ----
    def add_admin_scope(self, s: AdminScope) -> None:
        self.db.execute("INSERT INTO admin_scopes(id,tenant_id,user_id,org_node_id) VALUES(?,?,?,?)",
                        (s.id, s.tenant_id, s.user_id, s.org_node_id)); self.db.commit()

    def admin_scopes_of(self, tenant_id: str, user_id: str) -> list[AdminScope]:
        rows = self.db.execute("SELECT * FROM admin_scopes WHERE tenant_id=? AND user_id=?", (tenant_id, user_id)).fetchall()
        return [AdminScope(r["id"], r["tenant_id"], r["user_id"], r["org_node_id"]) for r in rows]

    # ---- audit ----
    def append_audit(self, e: AuditEntry) -> None:
        self.db.execute(
            "INSERT INTO audit_log(id,tenant_id,user_id,grant_id,action,target,ok,reason,ts,prev_hash,hash) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (e.id, e.tenant_id, e.user_id, e.grant_id, e.action, e.target, int(e.ok), e.reason, e.ts, e.prev_hash, e.hash))
        self.db.commit()

    def last_audit_hash(self, tenant_id: str) -> str:
        r = self.db.execute("SELECT hash FROM audit_log WHERE tenant_id=? ORDER BY ts DESC LIMIT 1", (tenant_id,)).fetchone()
        return r["hash"] if r else ""

    def list_audit(self, tenant_id: str, limit: int = 100) -> list[AuditEntry]:
        rows = self.db.execute("SELECT * FROM audit_log WHERE tenant_id=? ORDER BY ts DESC LIMIT ?", (tenant_id, limit)).fetchall()
        return [AuditEntry(r["id"], r["tenant_id"], r["user_id"], r["grant_id"], r["action"], r["target"],
                           bool(r["ok"]), r["reason"] or "", r["ts"], r["prev_hash"] or "", r["hash"]) for r in rows]
