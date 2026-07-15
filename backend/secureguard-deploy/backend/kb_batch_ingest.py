"""
backend.kb_batch_ingest — 知识库批量入库编排(可离线测)。

多文件/zip → 递归解压 → 按扩展名查映射表路由解析器 → 抽文本 → 入指定知识库 → 报告。
限制(文件数/单文件MB/总MB/OCR开关/语言)由管理后台配置传入,不写死。
解析器与 ingest 都注入,故本模块可用桩离线测;真实解析在装库的服务器跑。
"""
from __future__ import annotations

import io
import os
import zipfile
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .kb_parser_registry import ParserRegistry

# (filename, data:bytes, registry, cfg) -> text ;由上层用 doc_parsers 实现并注入
ExtractFn = Callable[[str, bytes, ParserRegistry, "IngestConfig"], str]
# (kb_id, doc_id, text) -> None ;注入现有 kb_service.ingest_text
IngestFn = Callable[[str, str, str], None]


@dataclass
class IngestConfig:
    max_files: int = 50
    max_file_mb: int = 20
    max_total_mb: int = 100
    ocr_enabled: bool = False
    ocr_lang: str = "ch"

    @property
    def max_file_bytes(self) -> int: return self.max_file_mb * 1024 * 1024
    @property
    def max_total_bytes(self) -> int: return self.max_total_mb * 1024 * 1024


@dataclass
class IngestReport:
    ingested: list[dict] = field(default_factory=list)   # {file, chars}
    skipped: list[dict] = field(default_factory=list)    # {file, reason}
    failed: list[dict] = field(default_factory=list)     # {file, reason}

    def summary(self): return {"ingested": len(self.ingested), "skipped": len(self.skipped), "failed": len(self.failed)}
    def public(self): return {"summary": self.summary(), "ingested": self.ingested, "skipped": self.skipped, "failed": self.failed}


def _iter_files(filename: str, data: bytes):
    """若是 zip,递归吐出 (内部名, bytes);否则吐出自身。忽略目录与 __MACOSX。"""
    if filename.lower().endswith(".zip"):
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            yield (filename, None); return
        for n in zf.namelist():
            if n.endswith("/") or "__MACOSX" in n:
                continue
            inner = zf.read(n)
            if n.lower().endswith(".zip"):       # 递归嵌套 zip
                yield from _iter_files(n, inner)
            else:
                yield (n.split("/")[-1], inner)
    else:
        yield (filename, data)


def ingest_batch(
    uploads: list[tuple[str, bytes]],          # [(filename, data), ...]
    *,
    kb_id: str,
    registry: ParserRegistry,
    extract_fn: ExtractFn,
    ingest_fn: IngestFn,
    cfg: IngestConfig,
) -> IngestReport:
    rep = IngestReport()
    total = 0
    count = 0

    flat: list[tuple[str, Optional[bytes]]] = []
    for fn, data in uploads:
        flat.extend(_iter_files(fn, data))

    for name, data in flat:
        if count >= cfg.max_files:
            rep.skipped.append({"file": name, "reason": f"超过单次文件数上限 {cfg.max_files}"})
            continue
        if data is None:
            rep.failed.append({"file": name, "reason": "无法读取/损坏的压缩包"})
            continue
        ext = os.path.splitext(name)[1].lower()
        mapping = registry.resolve(ext)
        if not mapping:
            rep.skipped.append({"file": name, "reason": f"不支持的类型 {ext}(可在映射表添加)"})
            continue
        if len(data) > cfg.max_file_bytes:
            rep.skipped.append({"file": name, "reason": f"单文件超 {cfg.max_file_mb}MB"})
            continue
        if total + len(data) > cfg.max_total_bytes:
            rep.skipped.append({"file": name, "reason": f"累计超 {cfg.max_total_mb}MB,余下未处理"})
            break
        try:
            text = extract_fn(name, data, registry, cfg)
            if not text.strip():
                rep.skipped.append({"file": name, "reason": "未抽取到文本(可能是扫描件,需开 OCR)"})
                continue
            ingest_fn(kb_id, name, text)
            rep.ingested.append({"file": name, "chars": len(text)})
            total += len(data); count += 1
        except Exception as e:
            rep.failed.append({"file": name, "reason": str(e)[:200]})
    return rep
