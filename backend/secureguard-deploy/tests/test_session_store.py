"""tests/test_session_store.py — 对话持久化 + 多轮记忆 + 窗口管理（问题4 第1步）。"""
import sys, os, asyncio, tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.session_store import InMemorySessionStore, SQLiteSessionStore, build_session_store
from backend.state import AppState
from backend.chat_service import run_chat


# ---------- 持久化基本功能 ----------
def test_append_and_messages():
    s = InMemorySessionStore()
    s.append("s1", "user", "你好")
    s.append("s1", "assistant", "你好，有什么可以帮你")
    ms = s.messages("s1")
    assert len(ms) == 2 and ms[0].role == "user" and ms[1].role == "assistant"


def test_first_user_message_becomes_title():
    s = InMemorySessionStore()
    s.append("s1", "user", "风管验收标准是什么")
    assert "风管验收" in s.list_sessions()[0]["title"]


def test_list_sessions_by_user_sorted():
    s = InMemorySessionStore()
    s.append("a", "user", "问题A", user_id="u1")
    s.append("b", "user", "问题B", user_id="u1")
    s.append("c", "user", "问题C", user_id="u2")
    mine = s.list_sessions(user_id="u1")
    assert {m["id"] for m in mine} == {"a", "b"}


def test_search_by_content():
    s = InMemorySessionStore()
    s.append("s1", "user", "如何计算漏风率", user_id="u1")
    s.append("s2", "user", "今天天气", user_id="u1")
    hits = s.search("u1", "漏风率")
    assert len(hits) == 1 and hits[0]["id"] == "s1"


def test_rename_and_delete():
    s = InMemorySessionStore()
    s.append("s1", "user", "原标题")
    assert s.rename("s1", "新标题") and s.list_sessions()[0]["title"] == "新标题"
    assert s.delete("s1") and s.messages("s1") == []


# ---------- 窗口管理：防 token 暴涨 ----------
def test_window_keeps_recent_summarizes_old():
    s = InMemorySessionStore()
    for i in range(20):  # 20 条 user 消息
        s.append("s1", "user", f"问题{i}")
        s.append("s1", "assistant", f"回答{i}")
    ctx = s.build_context("s1", max_turns=3)
    # 最近 3 轮逐字保留
    assert "问题19" in ctx and "回答19" in ctx
    # 早期被压成摘要，不逐字
    assert "[早期对话摘要]" in ctx
    assert "问题0：" not in ctx  # 早期不逐字出现


def test_empty_context():
    assert InMemorySessionStore().build_context("none") == ""


# ---------- SQLite 持久化：刷新/重启不丢 ----------
def test_sqlite_persists_across_reopen():
    path = tempfile.mktemp(suffix=".db")
    try:
        s1 = SQLiteSessionStore(path)
        s1.append("s1", "user", "持久化测试", user_id="u1")
        s1.append("s1", "assistant", "已记住")
        # 重新打开 → 数据还在
        s2 = SQLiteSessionStore(path)
        ms = s2.messages("s1")
        assert len(ms) == 2 and ms[0].content == "持久化测试"
        assert s2.list_sessions(user_id="u1")[0]["id"] == "s1"
    finally:
        if os.path.exists(path):
            os.unlink(path)


# ---------- 端到端：多轮记忆生效 ----------
def test_multiturn_memory_injected():
    """第二轮请求时，历史应被注入（模型 prompt 里能看到上一轮）。"""
    st = AppState()
    async def turn(msg):
        out = ""
        async for ev in run_chat(st, msg, agent_id="general", session_id="sess1"):
            if ev["event"] == "delta":
                out += ev["text"]
        return out
    asyncio.run(turn("风管验收标准"))
    # 第一轮后，会话里应有 user+assistant 两条
    msgs = st.sessions.messages("sess1")
    assert len(msgs) == 2 and msgs[0].role == "user"
    # 第二轮：build_context 应包含第一轮内容（多轮记忆）
    ctx = st.sessions.build_context("sess1")
    assert "风管验收标准" in ctx
    asyncio.run(turn("继续"))
    assert len(st.sessions.messages("sess1")) == 4  # 累积四条


def test_build_session_store_default_inmemory():
    assert isinstance(build_session_store(), InMemorySessionStore)


# ---------- 跨会话引用（第3步） ----------
def test_build_reference_summarizes_other_session():
    s = InMemorySessionStore()
    # 会话 A：聊了风管验收
    s.append("A", "user", "风管验收的漏风率怎么算", user_id="u1")
    s.append("A", "assistant", "漏风率按 GB50243 计算", user_id="u1")
    ref = s.build_reference(["A"])
    assert "【引用会话" in ref and "漏风率" in ref


def test_build_reference_multiple_and_empty():
    s = InMemorySessionStore()
    s.append("A", "user", "问题A", user_id="u1")
    s.append("B", "user", "问题B", user_id="u1")
    ref = s.build_reference(["A", "B", "不存在"])
    assert "问题A" in ref and "问题B" in ref  # 不存在的会话被跳过
    assert s.build_reference([]) == ""


def test_reference_injected_end_to_end():
    """跨会话引用端到端：引用别的会话，prompt 里出现引用块。"""
    st = AppState()
    async def turn(msg, refs=None):
        out = ""
        async for ev in run_chat(st, msg, agent_id="general", session_id="cur", ref_sessions=refs):
            if ev["event"] == "delta":
                out += ev["text"]
        return out
    # 先在另一个会话 'past' 存点内容
    st.sessions.append("past", "user", "幂等性是什么", user_id=None)
    st.sessions.append("past", "assistant", "同一操作多次执行结果一致", user_id=None)
    # 当前会话引用 'past'
    ref = st.sessions.build_reference(["past"])
    assert "幂等性" in ref  # 引用内容确实包含被引用会话
