"""tests/test_sandbox.py — 沙箱执行器（问题2）。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.sandbox_executor import SandboxExecutor, build_executor


def test_normal_code_runs():
    r = SandboxExecutor(timeout=5).execute("print(sorted([3,1,2]))")
    assert r["available"] and r["exit_code"] == 0 and "[1, 2, 3]" in r["stdout"]


def test_error_code_captured():
    r = SandboxExecutor(timeout=5).execute("1 + 'a'")
    assert r["exit_code"] != 0 and "TypeError" in r["stderr"]


def test_timeout_enforced():
    r = SandboxExecutor(timeout=2).execute("while True: pass")
    assert r["timed_out"] and "timeout" in r["error"]


def test_unavailable_degrades_gracefully():
    r = SandboxExecutor(available=False).execute("print(1)")
    assert r["available"] is False and r["error"] == "sandbox_not_available"


def test_unsupported_language():
    r = SandboxExecutor().execute("console.log(1)", language="javascript")
    assert "unsupported_language" in r["error"]


def test_build_executor_env_toggle(monkeypatch=None):
    os.environ["SANDBOX_ENABLED"] = "0"
    try:
        assert build_executor().available is False
    finally:
        del os.environ["SANDBOX_ENABLED"]


def test_docker_backend_builds_correct_command(monkeypatch=None):
    """Docker 后端：构造正确的隔离命令（不真跑 docker，只校验参数齐全）。"""
    import backend.sandbox_executor as se
    captured = {}
    class FakeCompleted:
        returncode = 0; stdout = "[1, 2, 3]"; stderr = ""
    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return FakeCompleted()
    orig = se.subprocess.run
    se.subprocess.run = fake_run
    try:
        ex = se.SandboxExecutor(backend="docker", mem_mb=128)
        r = ex.execute("print(1)")
        cmd = " ".join(captured["cmd"])
        # 全套隔离参数都在
        assert "--network=none" in cmd          # 禁网
        assert "--read-only" in cmd             # 只读根
        assert "--cap-drop=ALL" in cmd          # 丢能力
        assert "--security-opt=no-new-privileges" in cmd
        assert "--memory=128m" in cmd
        assert "--pids-limit=64" in cmd
        assert "65534:65534" in cmd             # 非 root
        assert r["backend"] == "docker" and r["exit_code"] == 0
    finally:
        se.subprocess.run = orig


def test_docker_not_found_degrades():
    import backend.sandbox_executor as se
    orig = se.subprocess.run
    def boom(*a, **k): raise FileNotFoundError()
    se.subprocess.run = boom
    try:
        r = se.SandboxExecutor(backend="docker").execute("print(1)")
        assert r["available"] is False and "docker_not_found" in r["error"]
    finally:
        se.subprocess.run = orig


def test_build_executor_docker_env():
    os.environ["SANDBOX_BACKEND"] = "docker"
    os.environ["SANDBOX_IMAGE"] = "python:3.12-slim"
    try:
        ex = build_executor()
        assert ex.backend == "docker" and ex.image == "python:3.12-slim"
    finally:
        del os.environ["SANDBOX_BACKEND"]; del os.environ["SANDBOX_IMAGE"]
