"""tests/test_evolution_gates.py — 进化补丁门禁单测。"""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from secureguard.evolution_gates import EvolutionGates, Patch


def _repo():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "config", "plane1"))
    os.makedirs(os.path.join(d, "secureguard"))
    with open(os.path.join(d, "config", "plane1", "failure-prevention.md"), "w") as f:
        f.write("# existing rules\n- rule A\n")
    with open(os.path.join(d, "config", "redlines.yaml"), "w") as f:
        f.write("version: 1\n")
    return d


def test_g1_blocks_plane0():
    d = _repo()
    g = EvolutionGates(d)
    out = g.apply(Patch("config/redlines.yaml", "replace", "evil: true"), lambda: True)
    assert not out.accepted and out.rejected_by == "G1_plane0_immutable"
    shutil.rmtree(d)


def test_g2_blocks_non_append_plane1():
    d = _repo()
    g = EvolutionGates(d)
    out = g.apply(Patch("config/plane1/failure-prevention.md", "replace", "wiped"), lambda: True)
    assert not out.accepted and out.rejected_by == "G2_append_only"
    shutil.rmtree(d)


def test_append_plane1_accepted_and_preserves_existing():
    d = _repo()
    g = EvolutionGates(d)
    out = g.apply(Patch("config/plane1/failure-prevention.md", "append", "- rule B (new)"),
                  lambda: True)
    assert out.accepted
    with open(os.path.join(d, "config", "plane1", "failure-prevention.md")) as f:
        txt = f.read()
    assert "rule A" in txt and "rule B (new)" in txt  # 既有内容保留
    shutil.rmtree(d)


def test_g3_syntax_gate_rejects_bad_python():
    d = _repo()
    g = EvolutionGates(d)
    out = g.apply(Patch("secureguard/new_mod.py", "create", "def f(:\n  pass"), lambda: True)
    assert not out.accepted and out.rejected_by == "G3_syntax"
    shutil.rmtree(d)


def test_g4_test_gate_rolls_back_on_failure():
    d = _repo()
    g = EvolutionGates(d)
    target = "config/plane1/failure-prevention.md"
    out = g.apply(Patch(target, "append", "- rule C"), run_tests=lambda: False)
    assert not out.accepted and out.rejected_by == "G4_test_gate" and out.rolled_back
    with open(os.path.join(d, target)) as f:
        txt = f.read()
    assert "rule C" not in txt  # 已回滚
    shutil.rmtree(d)


def test_create_new_py_with_valid_syntax_and_tests():
    d = _repo()
    g = EvolutionGates(d)
    out = g.apply(Patch("secureguard/helper.py", "create", "def add(a, b):\n    return a + b\n"),
                  lambda: True)
    assert out.accepted and os.path.exists(os.path.join(d, "secureguard", "helper.py"))
    shutil.rmtree(d)
