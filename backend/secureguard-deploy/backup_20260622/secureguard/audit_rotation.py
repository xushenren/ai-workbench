"""secureguard.audit_rotation — 审计保留策略（回答咨询 #6）。

在 AuditLogger 之上加：按尺寸轮转 + 备份数上限 + 按天数过期清理。
继承原 AuditLogger，写入路径不变，只在每次落盘后检查是否需要轮转/清理。
"""
from __future__ import annotations

import glob
import os
import time
from typing import Optional

from .l4_audit import AuditEntry, AuditLogger


class RotatingAuditLogger(AuditLogger):
    """带保留策略的审计记录器。

    - max_bytes：单文件超过即轮转为 path.1, path.2 ...
    - backup_count：保留的历史分卷数上限，超出删最旧
    - retention_days：按 mtime 超期的分卷直接清理
    """

    def __init__(self, path: str, max_bytes: int = 5_000_000,
                 backup_count: int = 5, retention_days: Optional[float] = 30.0) -> None:
        super().__init__(path=path)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.retention_days = retention_days

    def log(self, entry: AuditEntry) -> AuditEntry:
        e = super().log(entry)
        if self.path:
            self._maybe_rotate()
            self._enforce_retention()
        return e

    def _maybe_rotate(self) -> None:
        try:
            if os.path.getsize(self.path) < self.max_bytes:
                return
        except OSError:
            return
        # 滚动：path.(n-1) -> path.n，最旧的丢弃
        for i in range(self.backup_count - 1, 0, -1):
            src, dst = f"{self.path}.{i}", f"{self.path}.{i+1}"
            if os.path.exists(src):
                os.replace(src, dst)
        if os.path.exists(self.path):
            os.replace(self.path, f"{self.path}.1")
        # 超出 backup_count 的分卷删除
        for old in glob.glob(f"{self.path}.*"):
            try:
                idx = int(old.rsplit(".", 1)[1])
                if idx > self.backup_count:
                    os.remove(old)
            except (ValueError, OSError):
                continue

    def _enforce_retention(self) -> None:
        if not self.retention_days:
            return
        cutoff = time.time() - self.retention_days * 86400
        for f in glob.glob(f"{self.path}.*"):
            try:
                if os.path.getmtime(f) < cutoff:
                    os.remove(f)
            except OSError:
                continue
