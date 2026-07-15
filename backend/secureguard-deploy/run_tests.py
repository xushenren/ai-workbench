"""run_tests.py — 离线测试 runner（无需 pytest）。

发现 tests/ 下所有 test_*.py 模块里的 test_* 函数并执行，
打印通过/失败汇总，失败时以非零码退出。若环境装了 pytest，
也可直接 `python -m pytest tests/`。
"""
import importlib.util
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(ROOT, "tests")
sys.path.insert(0, ROOT)


def _load(path):
    name = "t_" + os.path.basename(path)[:-3]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    passed = failed = 0
    failures = []
    for fn in sorted(os.listdir(TESTS)):
        if not (fn.startswith("test_") and fn.endswith(".py")):
            continue
        mod = _load(os.path.join(TESTS, fn))
        for attr in sorted(dir(mod)):
            if not attr.startswith("test_"):
                continue
            func = getattr(mod, attr)
            if not callable(func):
                continue
            try:
                func()
                passed += 1
                print(f"  PASS  {fn}::{attr}")
            except Exception as e:
                failed += 1
                failures.append((f"{fn}::{attr}", e, traceback.format_exc()))
                print(f"  FAIL  {fn}::{attr}  -> {e}")
    print("\n" + "=" * 60)
    print(f"  {passed} passed, {failed} failed")
    print("=" * 60)
    if failures:
        for name, e, tb in failures:
            print(f"\n--- {name} ---\n{tb}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
