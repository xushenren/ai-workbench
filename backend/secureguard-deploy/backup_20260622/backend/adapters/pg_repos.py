"""backend.adapters.pg_repos — Postgres 持久化（DDL + 仓储）。

⚠️ 未在沙箱测试：需 Postgres + asyncpg。本文件给出：
  1) 建表 DDL（与 CONTRACT.md §5 一致）；
  2) Database 连接池封装；
  3) 两个代表性仓储（AuditRepo / QuotaRepo）作为范式。

接入指引（B7+）：把 AuthService/AgentService/KBService 内部的内存 dict 替换为对应仓储调用，
**对外方法签名不变**，因此 chat_service / 端点层无需改动。其余表(users/agents/kb)按同样
范式补仓储即可。asyncpg 懒加载。
"""
from __future__ import annotations

from typing import Any, List, Optional

DDL = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, phone TEXT UNIQUE, wechat_openid TEXT,
  role TEXT NOT NULL, dept_id TEXT, dept_admin BOOLEAN DEFAULT FALSE,
  pwd_salt BYTEA, pwd_hash TEXT, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY, name TEXT, description TEXT, domain TEXT,
  system_prompt TEXT, model TEXT, fallback_model TEXT,
  compute_policy JSONB, scope TEXT, free_quota JSONB,
  visibility TEXT, owner_id TEXT, status TEXT, dept_id TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS quotas (
  user_id TEXT, agent_id TEXT, period TEXT,
  used_tokens BIGINT DEFAULT 0, limit_tokens BIGINT,
  locked BOOLEAN DEFAULT FALSE, freeze_until TIMESTAMPTZ,
  PRIMARY KEY (user_id, agent_id, period)
);
CREATE TABLE IF NOT EXISTS audit (
  id BIGSERIAL PRIMARY KEY, session_id TEXT, stage TEXT, decision TEXT,
  reason TEXT, input_hash TEXT, output_hash TEXT, rule_id TEXT, tier TEXT,
  latency_ms INT, prev_hash CHAR(64), entry_hash CHAR(64),
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS knowledge_bases (
  id TEXT PRIMARY KEY, name TEXT, type TEXT, tenant_id TEXT,
  visibility TEXT, owner_id TEXT, allowed_roles JSONB, dept_id TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
"""


class Database:
    """asyncpg 连接池封装。"""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._pool: Optional[Any] = None

    async def connect(self) -> None:  # pragma: no cover - 需真实 PG
        try:
            import asyncpg  # 懒加载
        except Exception as e:
            raise RuntimeError("Postgres 仓储需要 asyncpg：pip install asyncpg") from e
        self._pool = await asyncpg.create_pool(self.dsn)
        async with self._pool.acquire() as con:
            await con.execute(DDL)

    @property
    def pool(self) -> Any:  # pragma: no cover
        if self._pool is None:
            raise RuntimeError("Database 未连接，先 await connect()")
        return self._pool


class AuditRepo:
    """审计落 PG。append 时携带哈希链字段（与 l4_audit 一致）。"""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def append(self, e: Any) -> None:  # pragma: no cover
        async with self.db.pool.acquire() as con:
            await con.execute(
                """INSERT INTO audit(session_id,stage,decision,reason,input_hash,
                   output_hash,rule_id,tier,latency_ms,prev_hash,entry_hash)
                   VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)""",
                e.session_id, e.stage, e.decision, e.reason, e.input_hash,
                e.output_hash, e.extra.get("rule_id", ""), e.extra.get("tier", ""),
                e.latency_ms, e.prev_hash, e.entry_hash,
            )

    async def recent(self, n: int = 10) -> List[dict]:  # pragma: no cover
        async with self.db.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT entry_hash,stage,decision,created_at FROM audit ORDER BY id DESC LIMIT $1", n)
            return [dict(r) for r in rows]


class QuotaRepo:
    """配额落 PG（原子扣减用行锁 / UPDATE...RETURNING）。Redis 版更适合高并发。"""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def consume(self, user_id: str, agent_id: str, period: str,
                      tokens: int, limit: int) -> dict:  # pragma: no cover
        async with self.db.pool.acquire() as con:
            async with con.transaction():
                row = await con.fetchrow(
                    """INSERT INTO quotas(user_id,agent_id,period,used_tokens,limit_tokens)
                       VALUES($1,$2,$3,$4,$5)
                       ON CONFLICT (user_id,agent_id,period) DO UPDATE
                         SET used_tokens = quotas.used_tokens + EXCLUDED.used_tokens
                       RETURNING used_tokens, limit_tokens, locked""",
                    user_id, agent_id, period, tokens, limit)
                used, lim, locked = row["used_tokens"], row["limit_tokens"], row["locked"]
                if used >= lim and not locked:
                    await con.execute(
                        "UPDATE quotas SET locked=TRUE WHERE user_id=$1 AND agent_id=$2 AND period=$3",
                        user_id, agent_id, period)
                    locked = True
                return {"used": used, "limit": lim, "locked": locked}


# ====================================================================== #
# 微信 OAuth 真实实现（替换 auth.wechat_callback 的桩）
# ====================================================================== #
async def wechat_exchange(code: str, appid: str, secret: str) -> dict:  # pragma: no cover
    """code → access_token + openid。需联网 + 真实密钥。"""
    try:
        import httpx
    except Exception as e:
        raise RuntimeError("微信 OAuth 需要 httpx") from e
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get("https://api.weixin.qq.com/sns/oauth2/access_token", params={
            "appid": appid, "secret": secret, "code": code, "grant_type": "authorization_code",
        })
        r.raise_for_status()
        data = r.json()
        if "openid" not in data:
            raise RuntimeError(f"微信换取失败: {data}")
        return {"openid": data["openid"], "access_token": data.get("access_token", "")}
