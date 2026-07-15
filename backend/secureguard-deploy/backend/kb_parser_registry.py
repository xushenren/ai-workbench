"""
backend.kb_parser_registry — 文件类型 ↔ 解析器 映射表(可配置、可扩展)。

内置常见办公文档映射;管理员可手动添加,或用 md/excel 批量导入映射
(扩展名 → 解析器名/外部工具),从而支持专有格式而无需改代码。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# 内置解析器名(对应 doc_parsers 里的函数);external 表示走外部命令
BUILTIN = {
    ".pdf": "pdf", ".docx": "docx", ".doc": "docx",
    ".xlsx": "xlsx", ".xls": "xlsx", ".csv": "csv",
    ".pptx": "pptx", ".ppt": "pptx",
    ".txt": "text", ".md": "text", ".markdown": "text",
    ".png": "ocr_image", ".jpg": "ocr_image", ".jpeg": "ocr_image",
}


@dataclass
class ParserMapping:
    """一条映射:扩展名 → 解析器(内置名)或外部工具命令。"""
    ext: str
    parser: str = ""            # 内置解析器名
    external_cmd: str = ""      # 外部命令模板,如 'dwg2txt {input} {output}';二选一
    note: str = ""


class ParserRegistry:
    def __init__(self) -> None:
        self._map: dict[str, ParserMapping] = {
            e: ParserMapping(e, parser=p) for e, p in BUILTIN.items()
        }

    def resolve(self, ext: str) -> Optional[ParserMapping]:
        return self._map.get(ext.lower())

    def add(self, ext: str, *, parser: str = "", external_cmd: str = "", note: str = "") -> ParserMapping:
        ext = ext.lower()
        if not ext.startswith("."):
            ext = "." + ext
        if not parser and not external_cmd:
            raise ValueError("parser 或 external_cmd 至少给一个")
        m = ParserMapping(ext, parser=parser, external_cmd=external_cmd, note=note)
        self._map[ext] = m
        return m

    def remove(self, ext: str) -> bool:
        return self._map.pop(ext.lower(), None) is not None

    def list(self) -> list[ParserMapping]:
        return sorted(self._map.values(), key=lambda m: m.ext)

    def import_rows(self, rows: list[dict]) -> int:
        """批量导入映射。行:{ext, parser?, external_cmd?, note?}。返回导入条数。"""
        n = 0
        for r in rows:
            ext = (r.get("ext") or r.get("扩展名") or "").strip()
            if not ext:
                continue
            self.add(ext, parser=(r.get("parser") or "").strip(),
                     external_cmd=(r.get("external_cmd") or "").strip(),
                     note=(r.get("note") or "").strip())
            n += 1
        return n

    def supported_exts(self) -> list[str]:
        return sorted(self._map.keys())
