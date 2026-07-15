"""tests/test_model_service.py — 模型配置（①）。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.model_service import ModelService, _mask


def test_seed_builtin_exists():
    s = ModelService()
    ids = [m["id"] for m in s.list_models()]
    assert "builtin" in ids


def test_create_and_list():
    s = ModelService()
    m = s.create("DeepSeek-V3", "https://api.deepseek.com/v1", "sk-secret123", "deepseek-chat")
    assert m["name"] == "DeepSeek-V3" and m["model"] == "deepseek-chat"
    assert any(x["id"] == m["id"] for x in s.list_models())


def test_api_key_masked_never_plaintext():
    s = ModelService()
    m = s.create("X", "url", "sk-supersecretkey", "x")
    assert "supersecret" not in str(m)        # 明文 key 不回传
    assert m["api_key_masked"].endswith("tkey")  # 只留末4位


def test_create_validates_required():
    s = ModelService()
    try:
        s.create("", "url", "k", "")          # 名字和标识空
        assert False
    except ValueError:
        pass


def test_update_changes_fields_but_keeps_key_if_blank():
    s = ModelService()
    m = s.create("X", "url", "sk-original", "x")
    # 更新名字，不传 key → key 不变
    s.update(m["id"], name="Y", api_key="")
    cfg = s.get(m["id"])
    assert cfg.name == "Y" and cfg.api_key == "sk-original"
    # 传新 key → 更新
    s.update(m["id"], api_key="sk-new")
    assert s.get(m["id"]).api_key == "sk-new"


def test_builtin_protected():
    s = ModelService()
    for op in (lambda: s.update("builtin", name="x"), lambda: s.delete("builtin")):
        try:
            op(); assert False
        except ValueError:
            pass


def test_resolve_falls_back_to_enabled():
    s = ModelService()
    m = s.create("A", "u", "k", "a")
    assert s.resolve(m["id"]).id == m["id"]       # 指定存在的
    assert s.resolve("nonexistent").enabled        # 不存在 → 回退到启用的
    s.update(m["id"], enabled=False)
    assert s.resolve(m["id"]).id != m["id"] or s.resolve(m["id"]).enabled  # 禁用的不被选


def test_list_selectable_excludes_disabled():
    s = ModelService()
    m = s.create("A", "u", "k", "a", enabled=False)
    sel = [x["id"] for x in s.list_selectable()]
    assert m["id"] not in sel and "builtin" in sel


def test_mask():
    assert _mask("sk-abcd1234").endswith("1234")
    assert _mask("") == ""
    assert _mask("ab") == "••••"
