"""secureguard.evolution_gates — 递归进化补丁门禁（回答咨询 #1 的"防破坏 + 回滚"）。

Refiner 产出的不是自由代码，而是受约束的 Patch。任何 patch 落盘前必须穿过这串门：

    G1 plane0_immutable   目标若属 Plane-0（红线/护栏/裁决/策略模块）→ 直接拒（R-12）
    G2 append_only_plane1 目标若在 config/plane1/ → 只允许 append，禁止改/删既有行
    G3 syntax_gate        .py 目标编译通过（语法门）
    G4 test_gate          应用后跑测试必须全绿（正确性门，Default-FAIL）
    G5 rollback           应用前快照，任一步失败即原子回滚

设计要点：门的顺序是"越不可逆/越危险越靠前"。G1/G2 是纯静态判定（最便宜、最该先跑），
G3 编译，G4 才真正应用并跑测试，G5 兜底回滚。纯标准库。
"""
from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

# Plane-0 保护清单：相对仓库根的路径前缀。命中即不可写。
PROTECTED_PREFIXES = (
    "config/arbitration-and-gates.md",
    "config/redlines.yaml",
    "config/domain_guards.yaml",
    "secureguard/l1_gate.py",        # 红线/护栏/裁决的代码载体
    "secureguard/retrieval_guard.py",
    "secureguard/evolution_gates.py",
)
# 仅允许 append 的 Plane-1 区域
PLANE1_PREFIX = "config/plane1/"


@dataclass
class Patch:
    """一个受约束的补丁。"""

    target: str                       # 相对仓库根的路径
    mode: str                         # append / replace / create
    content: str                      # append/create 的新增内容；replace 的全文
    old_content: Optional[str] = None  # replace 时的预期原文（乐观锁，可选）


@dataclass
class GateOutcome:
    accepted: bool
    rejected_by: str = ""
    reason: str = ""
    rolled_back: bool = False
    notes: List[str] = field(default_factory=list)


def _norm(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


class EvolutionGates:
    """补丁门禁。apply() 串起 G1..G5。"""

    def __init__(self, repo_root: str) -> None:
        self.root = os.path.abspath(repo_root)

    # ---- G1 ----
    def _g1_plane0(self, patch: Patch) -> Optional[str]:
        t = _norm(patch.target)
        for p in PROTECTED_PREFIXES:
            if t == p or t.startswith(p):
                return f"redline:R-12 目标属 Plane-0 不可写: {t}"
        return None

    # ---- G2 ----
    def _g2_append_only(self, patch: Patch) -> Optional[str]:
        t = _norm(patch.target)
        if t.startswith(PLANE1_PREFIX) and patch.mode != "append":
            return f"Plane-1 仅允许 append，收到 mode={patch.mode}"
        # append 模式对任何已存在文件都不得删改既有内容（天然满足），
        # replace 模式若改动 Plane-1 文件的既有行则违规（已被上面拦截）。
        return None

    # ---- G3 ----
    def _g3_syntax(self, patch: Patch, new_full_text: str) -> Optional[str]:
        if _norm(patch.target).endswith(".py"):
            try:
                compile(new_full_text, patch.target, "exec")
            except SyntaxError as e:
                return f"语法门失败: {e}"
        return None

    def _materialize(self, patch: Patch) -> Tuple[str, str]:
        """返回 (绝对路径, 应用后的完整文本)，不落盘。"""
        abspath = os.path.join(self.root, _norm(patch.target))
        existing = ""
        if os.path.exists(abspath):
            with open(abspath, encoding="utf-8") as f:
                existing = f.read()
        if patch.mode == "append":
            new_text = existing + ("\n" if existing and not existing.endswith("\n") else "") + patch.content
        elif patch.mode == "create":
            if existing:
                raise FileExistsError(f"create 目标已存在: {patch.target}")
            new_text = patch.content
        elif patch.mode == "replace":
            if patch.old_content is not None and existing != patch.old_content:
                raise ValueError("replace 乐观锁失败：原文已变更")
            new_text = patch.content
        else:
            raise ValueError(f"未知 mode: {patch.mode}")
        return abspath, new_text

    def apply(self, patch: Patch, run_tests: Callable[[], bool]) -> GateOutcome:
        """穿过 G1..G5。run_tests() 返回 True 表示测试全绿。"""
        notes: List[str] = []

        # G1 静态：Plane-0 不可变
        if (r := self._g1_plane0(patch)):
            return GateOutcome(False, "G1_plane0_immutable", r)
        notes.append("G1 通过：未触 Plane-0")

        # G2 静态：append-only
        if (r := self._g2_append_only(patch)):
            return GateOutcome(False, "G2_append_only", r)
        notes.append("G2 通过：Plane-1 约束满足")

        # 物化（不落盘）
        try:
            abspath, new_text = self._materialize(patch)
        except Exception as e:
            return GateOutcome(False, "materialize", str(e))

        # G3：语法门
        if (r := self._g3_syntax(patch, new_text)):
            return GateOutcome(False, "G3_syntax", r)
        notes.append("G3 通过：语法 OK")

        # G5 快照（先于落盘）
        snapshot = None
        existed = os.path.exists(abspath)
        if existed:
            fd, snapshot = tempfile.mkstemp(suffix=".bak")
            os.close(fd)
            shutil.copy2(abspath, snapshot)

        # 落盘
        os.makedirs(os.path.dirname(abspath), exist_ok=True)
        with open(abspath, "w", encoding="utf-8") as f:
            f.write(new_text)

        # G4：测试门（Default-FAIL）
        try:
            green = bool(run_tests())
        except Exception as e:
            green = False
            notes.append(f"测试执行异常: {e}")

        if not green:
            # G5 回滚
            if existed and snapshot:
                shutil.copy2(snapshot, abspath)
            elif not existed:
                os.remove(abspath)
            if snapshot and os.path.exists(snapshot):
                os.remove(snapshot)
            return GateOutcome(False, "G4_test_gate", "测试未通过，已回滚",
                               rolled_back=True, notes=notes)

        if snapshot and os.path.exists(snapshot):
            os.remove(snapshot)
        notes.append("G4 通过：测试全绿")
        return GateOutcome(True, "", "patch accepted", notes=notes)
