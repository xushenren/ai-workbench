"""tests/test_md_version_store.py — 思考 MD 版本管理 + 回滚。"""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.md_version_store import MdVersionStore


def _setup():
    """临时 thinking 目录 + 两个 md 文件。"""
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "main.md"), "w") as f:
        f.write("# main v1\n原始主思考法")
    with open(os.path.join(d, "domain-software.md"), "w") as f:
        f.write("# software v1\n原始代码法")
    return d


def test_seed_from_files():
    d = _setup()
    try:
        s = MdVersionStore(thinking_dir=d)
        s.init_from_files(["main", "domain-software"])
        assert set(s.list_md_names()) == {"main", "domain-software"}
        live = s.get_live("main")
        assert live and live["status"] == "live" and live["version"] == 1
        assert "原始主思考法" in live["content"]
    finally:
        shutil.rmtree(d)


def test_save_new_version_is_candidate():
    d = _setup()
    try:
        s = MdVersionStore(thinking_dir=d)
        s.init_from_files(["main"])
        v2 = s.save_version("main", "# main v2\n改进版", origin="manual", note="手动改进")
        assert v2["status"] == "candidate" and v2["version"] == 2
        # 存了候选但还没上线 → live 仍是 v1
        assert s.get_live("main")["version"] == 1
    finally:
        shutil.rmtree(d)


def test_set_live_writes_file():
    """设为上线 = 写回 .md 文件（热加载即时生效的关键）。"""
    d = _setup()
    try:
        s = MdVersionStore(thinking_dir=d)
        s.init_from_files(["main"])
        v2 = s.save_version("main", "# main v2\n全新内容XYZ", origin="manual")
        s.set_live(v2["id"])
        # 文件内容应已被写成 v2
        with open(os.path.join(d, "main.md")) as f:
            assert "全新内容XYZ" in f.read()
        # live 指针指向 v2，旧版归档
        assert s.get_live("main")["version"] == 2
        versions = s.list_versions("main")
        v1 = next(v for v in versions if v["version"] == 1)
        assert v1["status"] == "archived"
    finally:
        shutil.rmtree(d)


def test_rollback_writes_old_content():
    """回滚 = 把旧版写回文件。"""
    d = _setup()
    try:
        s = MdVersionStore(thinking_dir=d)
        s.init_from_files(["main"])
        v1_id = s.get_live("main")["id"]
        v2 = s.save_version("main", "# main v2\n新版", origin="manual")
        s.set_live(v2["id"])
        with open(os.path.join(d, "main.md")) as f:
            assert "新版" in f.read()
        # 回滚到 v1
        s.rollback("main", v1_id)
        with open(os.path.join(d, "main.md")) as f:
            content = f.read()
            assert "原始主思考法" in content and "新版" not in content
        assert s.get_live("main")["version"] == 1
    finally:
        shutil.rmtree(d)


def test_diff():
    d = _setup()
    try:
        s = MdVersionStore(thinking_dir=d)
        s.init_from_files(["main"])
        v1_id = s.get_live("main")["id"]
        v2 = s.save_version("main", "# main v1\n原始主思考法\n新增一行", origin="manual")
        result = s.diff(v1_id, v2["id"])
        assert result["added"] >= 1
        assert "新增一行" in result["diff"]
    finally:
        shutil.rmtree(d)


def test_version_line_ordering_and_live_flag():
    d = _setup()
    try:
        s = MdVersionStore(thinking_dir=d)
        s.init_from_files(["main"])
        v2 = s.save_version("main", "v2", origin="manual")
        v3 = s.save_version("main", "v3", origin="evolved", parent=v2["id"])
        s.set_live(v3["id"])
        versions = s.list_versions("main")
        # 降序排列，v3 在最前且 is_live
        assert versions[0]["version"] == 3 and versions[0]["is_live"] is True
        assert versions[0]["origin"] == "evolved" and versions[0]["parent"] == v2["id"]
    finally:
        shutil.rmtree(d)


def test_persistence_across_reload():
    """json 持久化：重建 store 后版本仍在。"""
    d = _setup()
    db = os.path.join(d, "data", "mdver.json")
    try:
        s1 = MdVersionStore(thinking_dir=d, db_path=db)
        s1.init_from_files(["main"])
        s1.save_version("main", "v2持久化", origin="manual")
        # 重建
        s2 = MdVersionStore(thinking_dir=d, db_path=db)
        assert len(s2.list_versions("main")) == 2
    finally:
        shutil.rmtree(d)


def test_audit_recorded():
    d = _setup()
    try:
        s = MdVersionStore(thinking_dir=d)
        s.init_from_files(["main"])
        v2 = s.save_version("main", "v2", origin="manual")
        s.set_live(v2["id"])
        actions = [a["action"] for a in s.audit_log("main")]
        assert "seed" in actions and "save_version" in actions and "set_live" in actions
    finally:
        shutil.rmtree(d)


def test_appstate_integration():
    """AppState 集成：md_versions 自动播种现有 thinking MD。"""
    import sys, os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from backend.state import AppState
    st = AppState()
    names = st.md_versions.list_md_names()
    # 现有 config/thinking 至少有 main 和 domain-software
    assert "main" in names
    live = st.md_versions.get_live("main")
    assert live is not None and live["status"] == "live"
