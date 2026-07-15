"""backend.session_store — 对话持久化 + 多轮记忆 + 窗口管理（问题4 第1步）。

为什么有窗口管理：多轮记忆 = 每轮把历史塞进 prompt。聊久了 token 暴涨甚至超模型
上下文窗。所以这里**保留最近 N 轮逐字 + 更早的压成摘要**，而不是无脑全塞——
这对"用便宜模型省 token"是必须的。

  - InMemorySessionStore：默认，纯 stdlib，可离线测。
  - SQLiteSessionStore：单文件持久化（刷新/重启不丢），stdlib sqlite3，可离线测。
  - PgSessionStore：Postgres 适配器 🔴 占位，你在服务器接（同接口）。

接口契约（三种实现一致）：
  create_session / append / messages / list_sessions / search / rename / delete
  build_context(session_id, max_turns) -> str   # 窗口管理后的多轮上下文
"""
from __future__ import annotations

import time
import os
import sqlite3
import threading
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

DEFAULT_MAX_TURNS = 6  # 逐字保留最近 6 轮（user+assistant）


@dataclass
class Msg:
    role: str
    content: str
    ts: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _title_from(text: str) -> str:
    t = text.strip().replace("\n", " ")
    return (t[:20] + "…") if len(t) > 20 else (t or "新对话")


def _summarize(older: List[Msg]) -> str:
    """早期消息压缩成一行摘要（确定性、无需模型）。真 LLM 摘要可后续替换此函数。"""
    topics = [m.content.strip().replace("\n", " ")[:18] for m in older if m.role == "user"]
    if not topics:
        return f"（更早有 {len(older)} 条消息）"
    return "用户先后问及：" + "；".join(topics[-6:])


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, Dict[str, Any]] = {}      # sid -> meta
        self._messages: Dict[str, List[Msg]] = {}           # sid -> [Msg]
        self._lock = threading.Lock()

    # ---------- 会话 ----------
    def create_session(self, session_id: str, user_id: Optional[str] = None,
                       title: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if session_id not in self._sessions:
                now = time.time()
                self._sessions[session_id] = {
                    "id": session_id, "user_id": user_id, "title": title or "新对话",
                    "created_at": now, "updated_at": now, "message_count": 0,
                }
                self._messages[session_id] = []
            return self._sessions[session_id]

    def append(self, session_id: str, role: str, content: str,
               user_id: Optional[str] = None) -> None:
        with self._lock:
            if session_id not in self._sessions:
                now = time.time()
                self._sessions[session_id] = {"id": session_id, "user_id": user_id,
                    "title": "新对话", "created_at": now, "updated_at": now, "message_count": 0}
                self._messages[session_id] = []
            self._messages[session_id].append(Msg(role, content, time.time()))
            meta = self._sessions[session_id]
            meta["updated_at"] = time.time()
            meta["message_count"] = len(self._messages[session_id])
            # 首条用户消息作标题
            if role == "user" and meta["title"] == "新对话":
                meta["title"] = _title_from(content)

    def messages(self, session_id: str) -> List[Msg]:
        with self._lock:
            return list(self._messages.get(session_id, []))

    def list_sessions(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            out = [m for m in self._sessions.values()
                   if user_id is None or m.get("user_id") == user_id]
            return sorted(out, key=lambda m: m["updated_at"], reverse=True)

    def search(self, user_id: Optional[str], query: str) -> List[Dict[str, Any]]:
        """按消息内容搜会话（命中标题或任一消息）。"""
        q = query.strip().lower()
        if not q:
            return []
        with self._lock:
            hits = []
            for sid, meta in self._sessions.items():
                if user_id is not None and meta.get("user_id") != user_id:
                    continue
                hay = meta["title"].lower() + " " + " ".join(
                    m.content.lower() for m in self._messages.get(sid, []))
                if q in hay:
                    hits.append(meta)
            return sorted(hits, key=lambda m: m["updated_at"], reverse=True)

    def rename(self, session_id: str, title: str) -> bool:
        with self._lock:
            if session_id not in self._sessions:
                return False
            self._sessions[session_id]["title"] = title
            return True

    def delete(self, session_id: str) -> bool:
        with self._lock:
            self._sessions.pop(session_id, None)
            return self._messages.pop(session_id, None) is not None

    # ---------- 窗口管理：多轮上下文 ----------
    def build_context(self, session_id: str, max_turns: int = DEFAULT_MAX_TURNS) -> str:
        """拼出窗口管理后的历史：早期摘要 + 最近 N 轮逐字。防 token 暴涨。"""
        msgs = self.messages(session_id)
        if not msgs:
            return ""
        keep = max_turns * 2
        recent, older = msgs[-keep:], msgs[:-keep]
        lines: List[str] = []
        if older:
            lines.append(f"[早期对话摘要] {_summarize(older)}")
        for m in recent:
            who = "用户" if m.role == "user" else "助手"
            lines.append(f"{who}：{m.content}")
        return "\n".join(lines)

    def build_reference(self, session_ids: List[str], max_recent: int = 2) -> str:
        """跨会话引用：把被引用会话压成"摘要 + 最近几轮"，带来源标注注入。

        刻意不逐字全文——逐字会 token 暴涨且与窗口管理冲突。每个被引用会话给：
          标题 + 早期摘要 + 最近 max_recent 轮，清楚标明"这是来自别的会话的参考"。
        """
        blocks: List[str] = []
        for sid in session_ids:
            msgs = self.messages(sid)
            if not msgs:
                continue
            meta = self._sessions.get(sid, {})
            title = meta.get("title", sid)
            keep = max_recent * 2
            recent, older = msgs[-keep:], msgs[:-keep]
            parts = [f"【引用会话：{title}】"]
            if older:
                parts.append(f"  摘要：{_summarize(older)}")
            for m in recent:
                who = "用户" if m.role == "user" else "助手"
                parts.append(f"  {who}：{m.content[:120]}")
            blocks.append("\n".join(parts))
        return "\n\n".join(blocks)


class SQLiteSessionStore(InMemorySessionStore):
    """单文件持久化（刷新/重启不丢）。stdlib sqlite3，可离线测。"""

    def __init__(self, path: str = ":memory:") -> None:
        super().__init__()
        # 自动创建父目录，避免 SESSION_DB 指向不存在目录时启动即崩
        if path not in (":memory:", "") and os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("""CREATE TABLE IF NOT EXISTS sessions(
            id TEXT PRIMARY KEY, user_id TEXT, title TEXT,
            created_at REAL, updated_at REAL)""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS messages(
            session_id TEXT, role TEXT, content TEXT, ts REAL)""")
        self._db.commit()
        self._load()

    def _load(self) -> None:
        for r in self._db.execute("SELECT id,user_id,title,created_at,updated_at FROM sessions"):
            self._sessions[r[0]] = {"id": r[0], "user_id": r[1], "title": r[2],
                "created_at": r[3], "updated_at": r[4], "message_count": 0}
            self._messages[r[0]] = []
        for r in self._db.execute("SELECT session_id,role,content,ts FROM messages ORDER BY ts"):
            self._messages.setdefault(r[0], []).append(Msg(r[1], r[2], r[3]))
        for sid, ms in self._messages.items():
            if sid in self._sessions:
                self._sessions[sid]["message_count"] = len(ms)

    def create_session(self, session_id, user_id=None, title=None):
        meta = super().create_session(session_id, user_id, title)
        self._db.execute("INSERT OR IGNORE INTO sessions VALUES(?,?,?,?,?)",
                         (meta["id"], meta["user_id"], meta["title"],
                          meta["created_at"], meta["updated_at"]))
        self._db.commit()
        return meta

    def append(self, session_id, role, content, user_id=None):
        super().append(session_id, role, content, user_id)
        meta = self._sessions[session_id]
        self._db.execute("INSERT OR IGNORE INTO sessions VALUES(?,?,?,?,?)",
                         (meta["id"], meta["user_id"], meta["title"],
                          meta["created_at"], meta["updated_at"]))
        self._db.execute("UPDATE sessions SET title=?,updated_at=? WHERE id=?",
                         (meta["title"], meta["updated_at"], session_id))
        self._db.execute("INSERT INTO messages VALUES(?,?,?,?)",
                         (session_id, role, content, time.time()))
        self._db.commit()

    def rename(self, session_id, title):
        ok = super().rename(session_id, title)
        if ok:
            self._db.execute("UPDATE sessions SET title=? WHERE id=?", (title, session_id))
            self._db.commit()
        return ok

    def delete(self, session_id):
        ok = super().delete(session_id)
        self._db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        self._db.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        self._db.commit()
        return ok


def build_session_store() -> InMemorySessionStore:
    """按环境变量选实现。默认内存；SESSION_DB=<path> → SQLite 持久化。

    韧性：SQLite 初始化失败（路径不可写/磁盘满等）时**降级为内存存储**并打警告，
    绝不让持久化层的配置问题导致整个后端启动失败（502）。
    """
    db = os.environ.get("SESSION_DB")
    if not db:
        # 只在 DATA_DIR 显式设置时默认持久化（生产）；否则内存（测试/开发，不污染）。
        data_dir = os.environ.get("DATA_DIR")
        if data_dir:
            db = os.path.join(data_dir, "sessions.db")
    if not db:
        return InMemorySessionStore()
    try:
        return SQLiteSessionStore(db)
    except Exception as e:  # 路径不可写、磁盘满等
        import sys
        print(f"[session_store] SQLite 初始化失败({e})，降级为内存存储（重启丢历史）。"
              f"请检查 {db} 的目录权限。", file=sys.stderr)
        return InMemorySessionStore()
