"""backend.agent_batch_import — 智能体 zip 批量导入(解析器无关,纯 stdlib)。

一个 zip 里一群智能体(每个 .md 一个)。本模块只负责:解包 → 遍历 .md →
逐个调注入的 parse_fn 解析 → 冲突处理 → 调注入的 create_fn 创建 → 产出报告。
单个文件的解析格式由 parse_fn 决定(可注入你现有的 parse_agent_md)。

安全:限制 zip 大小与文件数;忽略目录穿越/非 .md;单个文件失败不影响整体。
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

MAX_ZIP_BYTES = 20 * 1024 * 1024     # 20MB
MAX_FILES = 200
MAX_FILE_BYTES = 512 * 1024          # 单个 md ≤512KB

ParseFn = Callable[[str], Dict[str, Any]]
CreateFn = Callable[[Dict[str, Any]], Dict[str, Any]]   # payload -> 已建记录(含 id)
ExistsFn = Callable[[str], bool]                          # name -> 是否已存在
DeleteFn = Optional[Callable[[str], None]]               # name -> 删除(覆盖策略用)


@dataclass
class ImportReport:
    created: List[Dict[str, str]] = field(default_factory=list)   # {file, name, id}
    skipped: List[Dict[str, str]] = field(default_factory=list)   # {file, name, reason}
    failed: List[Dict[str, str]] = field(default_factory=list)    # {file, reason}

    def summary(self) -> Dict[str, int]:
        return {"created": len(self.created), "skipped": len(self.skipped), "failed": len(self.failed)}

    def public(self) -> Dict[str, Any]:
        return {"summary": self.summary(), "created": self.created,
                "skipped": self.skipped, "failed": self.failed}


def import_zip(
    zip_bytes: bytes,
    *,
    parse_fn: ParseFn,
    create_fn: CreateFn,
    exists_fn: ExistsFn,
    delete_fn: DeleteFn = None,
    conflict: str = "skip",          # skip | rename | overwrite
) -> ImportReport:
    rep = ImportReport()
    if len(zip_bytes) > MAX_ZIP_BYTES:
        rep.failed.append({"file": "(zip)", "reason": f"超过大小上限 {MAX_ZIP_BYTES//1024//1024}MB"})
        return rep
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        rep.failed.append({"file": "(zip)", "reason": "不是合法的 zip"})
        return rep

    names = [n for n in zf.namelist() if n.lower().endswith(".md") and not n.endswith("/")]
    if len(names) > MAX_FILES:
        rep.failed.append({"file": "(zip)", "reason": f"文件数超上限 {MAX_FILES}"})
        return rep

    for n in names:
        base = n.split("/")[-1]
        try:
            info = zf.getinfo(n)
            if info.file_size > MAX_FILE_BYTES:
                rep.failed.append({"file": base, "reason": "单文件过大"})
                continue
            content = zf.read(n).decode("utf-8", errors="replace")
            payload = parse_fn(content)
            name = (payload.get("name") or base).strip()

            if exists_fn(name):
                if conflict == "skip":
                    rep.skipped.append({"file": base, "name": name, "reason": "同名已存在"})
                    continue
                if conflict == "rename":
                    payload["name"] = _unique_name(name, exists_fn)
                elif conflict == "overwrite":
                    if delete_fn is None:
                        rep.skipped.append({"file": base, "name": name, "reason": "不支持覆盖"})
                        continue
                    delete_fn(name)

            rec = create_fn(payload)
            rep.created.append({"file": base, "name": payload.get("name", name),
                                "id": str(rec.get("id", ""))})
        except Exception as e:   # 单个失败不影响整体
            rep.failed.append({"file": base, "reason": str(e)[:200]})
    return rep


def _unique_name(name: str, exists_fn: ExistsFn) -> str:
    i = 2
    while exists_fn(f"{name} ({i})"):
        i += 1
        if i > 999:
            break
    return f"{name} ({i})"
