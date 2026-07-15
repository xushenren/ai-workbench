"""tests/test_agent_md.py — 智能体 MD 导入/导出。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.agent_md import parse_agent_md, to_agent_md, _split_frontmatter

SAMPLE = """---
name: 法务助手
domain: legal
icon: ⚖️
visibility: public
scope: domain_only
thinking: main
knowledge_bases: [kb_law, kb_contract]
model: deepseek-chat
description: 严谨的法务助手
---
你是一名严谨的法务助手。回答必须引用条款来源，不确定就明说。
"""


def test_parse_full_md():
    p = parse_agent_md(SAMPLE)
    assert p["name"] == "法务助手" and p["domain"] == "legal"
    assert p["visibility"] == "public" and p["scope"] == "domain_only"
    assert p["thinking"] == "main" and p["model"] == "deepseek-chat"
    assert p["knowledge_bases"] == ["kb_law", "kb_contract"] and p["kb_count"] == 2
    assert "引用条款来源" in p["system_prompt"]


def test_name_required():
    try:
        parse_agent_md("---\ndomain: x\n---\n正文")
        assert False
    except ValueError:
        pass


def test_invalid_visibility_falls_back():
    p = parse_agent_md("---\nname: A\nvisibility: hacker\nscope: weird\n---\n正文")
    assert p["visibility"] == "private" and p["scope"] == "domain_only"


def test_no_frontmatter_uses_body_as_prompt():
    # 没有 frontmatter 时应报错（无 name），但拆分正确
    fm, body = _split_frontmatter("没有frontmatter的纯文本")
    assert fm == "" and "纯文本" in body


def test_kb_single_string():
    p = parse_agent_md("---\nname: A\nknowledge_bases: kb_one\n---\n x")
    assert p["knowledge_bases"] == ["kb_one"]


def test_whitelist_ignores_unknown_fields():
    # owner_id/status 等不可由 MD 指定（防越权）
    p = parse_agent_md("---\nname: A\nowner_id: hacker\nstatus: published\n---\n x")
    assert "owner_id" not in p and "status" not in p


def test_export_roundtrip():
    p = parse_agent_md(SAMPLE)
    agent = {"name": p["name"], "domain": p["domain"], "icon": p["icon"],
             "visibility": p["visibility"], "scope": p["scope"], "tier": "tier1",
             "description": p["description"], "thinking": p["thinking"],
             "model": p["model"], "knowledge_bases": p["knowledge_bases"]}
    md = to_agent_md(agent, p["system_prompt"])
    # 导出的 MD 能再次解析回来
    p2 = parse_agent_md(md)
    assert p2["name"] == p["name"] and p2["knowledge_bases"] == p["knowledge_bases"]
    assert "引用条款来源" in p2["system_prompt"]


def test_end_to_end_create_via_md():
    from backend.state import AppState
    from backend.auth import AuthService
    st = AppState()
    a = st.auth
    tok, _ = a.login("13800000000", "admin123")
    caller = a.resolve(tok)
    p = parse_agent_md(SAMPLE)
    rec = st.agent_service.create(caller, p)
    assert rec["name"] == "法务助手"
