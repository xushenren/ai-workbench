"""secureguard.l4_audit — L4 审计日志。

设计原则：
  - 不存原文。输入/输出只存 SHA256 摘要，满足可追溯但不泄密。
  - 全链路：每层(L0..L4)的判定都记一条 AuditEntry。
  - 冲突可见：每次 arbitrate() 调用都写 ConflictLog（§0 第 2 条“永不静默”）。
  - 红线命中单独高亮记录，便于事后审计“红线违规次数=0”。
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# 链首（genesis）的 prev_hash：64 个 0，约定值，便于校验起点。
GENESIS_HASH = "0" * 64


@dataclass
class AuditEntry:
    """单条审计记录。input/output 只存哈希；prev_hash/entry_hash 构成防篡改链。"""

    stage: str                       # L0 / L1 / L2 / L3 / L4
    decision: str                    # PASS / ASK / BLOCK / ESCALATE
    reason: str = ""
    session_id: str = ""
    action_type: str = ""
    input_hash: str = ""
    output_hash: str = ""
    latency_ms: int = 0
    timestamp: str = field(default_factory=_now)
    extra: Dict[str, Any] = field(default_factory=dict)
    prev_hash: str = ""              # 上一条的 entry_hash（链接字段）
    entry_hash: str = ""             # 本条内容 + prev_hash 的 SHA256（防篡改指纹）

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def canonical(self) -> str:
        """规范化序列化（排除 entry_hash 自身），用于计算 entry_hash。

        排除 entry_hash 是因为它正是这段内容的哈希结果；包含 prev_hash，
        从而把"本条内容"与"上一条指纹"绑死——改任意历史条目都会断链。
        """
        d = self.to_dict()
        d.pop("entry_hash", None)
        return json.dumps(d, sort_keys=True, ensure_ascii=False)

    def compute_hash(self) -> str:
        return _sha256(self.canonical())


class AuditLogger:
    """线程安全的审计记录器。同时落 JSONL 文件与内存缓冲。"""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path
        self.entries: List[AuditEntry] = []
        self.conflicts: List[Dict[str, Any]] = []
        self.redline_hits: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._last_hash = GENESIS_HASH  # 链头：初始为 genesis
        if self.path:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            self._restore_last_hash()

    def _restore_last_hash(self) -> None:
        """重启/轮转后，从既有文件末行恢复链头，保证链跨进程/跨文件连续。"""
        try:
            if os.path.exists(self.path) and os.path.getsize(self.path) > 0:
                with open(self.path, "rb") as f:
                    last_line = f.readlines()[-1].decode("utf-8")
                self._last_hash = json.loads(last_line).get("entry_hash", GENESIS_HASH)
        except (OSError, IndexError, json.JSONDecodeError):
            pass  # 文件缺失/损坏时退回 genesis，verify 会暴露断裂

    # ---- 主审计写入 ----
    def log(self, entry: AuditEntry) -> AuditEntry:
        """记录一条审计条目（内存 + 可选 JSONL），并接入哈希链。"""
        with self._lock:
            entry.prev_hash = self._last_hash
            entry.entry_hash = entry.compute_hash()
            self._last_hash = entry.entry_hash
            self.entries.append(entry)
            if self.path:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        return entry

    def log_stage(self, *, stage: str, decision: str, reason: str = "",
                  session_id: str = "", action_type: str = "",
                  raw_input: str = "", raw_output: str = "",
                  latency_ms: int = 0, extra: Optional[Dict[str, Any]] = None) -> AuditEntry:
        """便捷封装：自动对原文做哈希，绝不存明文。"""
        return self.log(AuditEntry(
            stage=stage,
            decision=decision,
            reason=reason,
            session_id=session_id,
            action_type=action_type,
            input_hash=_sha256(raw_input) if raw_input else "",
            output_hash=_sha256(raw_output) if raw_output else "",
            latency_ms=latency_ms,
            extra=extra or {},
        ))

    # ---- 哈希链校验（D5）----
    def verify_chain(self, entries: Optional[List[AuditEntry]] = None,
                     require_genesis: bool = True) -> Dict[str, Any]:
        """校验内存中的审计链完整性。返回 {ok, broken_at, reason}。

        逐条重算 entry_hash 并检查 prev_hash 链接；任一处不符即定位断裂位置。
        require_genesis=True 时首条 prev_hash 必须为 genesis；轮转裁剪后只剩
        中段链时传 False，则从首条自身声明的 prev_hash 起验内部连续性
        （仍能检出任何段内篡改）。
        """
        items = entries if entries is not None else self.entries
        if not items:
            return {"ok": True, "broken_at": -1, "reason": "empty", "length": 0}
        expected_prev = GENESIS_HASH if require_genesis else items[0].prev_hash
        for i, e in enumerate(items):
            if e.prev_hash != expected_prev:
                return {"ok": False, "broken_at": i,
                        "reason": f"prev_hash 链接断裂：期望 {expected_prev[:12]}… 实际 {e.prev_hash[:12]}…"}
            recomputed = e.compute_hash()
            if recomputed != e.entry_hash:
                return {"ok": False, "broken_at": i,
                        "reason": f"第 {i} 条内容被篡改：entry_hash 不匹配"}
            expected_prev = e.entry_hash
        return {"ok": True, "broken_at": -1, "reason": "chain intact", "length": len(items)}

    @staticmethod
    def _load_entries(path: str) -> List[AuditEntry]:
        out: List[AuditEntry] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(AuditEntry(**json.loads(line)))
        return out

    @classmethod
    def verify_files(cls, paths_in_order: List[str],
                     require_genesis: bool = True) -> Dict[str, Any]:
        """跨文件校验：按时间顺序（最旧→最新）传入轮转分卷，校验整条链连续。

        轮转后链不在单文件内闭合——上一卷最后一条的 entry_hash 必须等于
        下一卷第一条的 prev_hash。本方法把多卷拼成一条逻辑链统一校验。
        若最早分卷已被保留策略裁剪，传 require_genesis=False 只验幸存段。
        """
        all_entries: List[AuditEntry] = []
        for p in paths_in_order:
            if os.path.exists(p):
                all_entries.extend(cls._load_entries(p))
        dummy = cls.__new__(cls)  # 不触发 __init__，仅借用 verify 逻辑
        return cls.verify_chain(dummy, all_entries, require_genesis=require_genesis)

    # ---- 冲突记录（arbitrate 调用） ----
    def record_conflict(self, conflict: Any, winner: Any,
                        human_feedback: Optional[str] = None) -> None:
        """记录一次仲裁冲突及裁决结果（§0 永不静默）。"""
        rec = {
            "timestamp": _now(),
            "conflict": [(r.tier, r.description) for r in conflict.rules],
            "winner": (winner.tier, winner.description),
            "surfaced_to_human": True,
            "human_feedback": human_feedback,
        }
        with self._lock:
            self.conflicts.append(rec)

    # ---- 红线命中（gate 调用） ----
    def note_redline(self, redline_id: str, action: Dict[str, Any]) -> None:
        """高亮记录红线命中，便于审计红线违规次数。"""
        rec = {
            "timestamp": _now(),
            "redline_id": redline_id,
            "action_type": action.get("type", ""),
            "action_hash": _sha256(json.dumps(action, sort_keys=True, ensure_ascii=False)),
        }
        with self._lock:
            self.redline_hits.append(rec)

    # ---- 查询辅助 ----
    def summary(self) -> Dict[str, Any]:
        """返回审计概览，benchmark 与运维可直接消费。"""
        decisions: Dict[str, int] = {}
        for e in self.entries:
            decisions[e.decision] = decisions.get(e.decision, 0) + 1
        return {
            "total_entries": len(self.entries),
            "decisions": decisions,
            "conflicts": len(self.conflicts),
            "redline_hits": len(self.redline_hits),
        }
