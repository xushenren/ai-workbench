"""backend.file_service — 文件上传（②）。

聊天可上传任意文件。本服务负责：存储、列表、按类型解析出"可喂给模型的文本"。

诚实边界（务必读）：
- 文本类（txt/md/csv/json/log/py 等）：直接读出文本 → 可喂模型。🟢
- 压缩包（zip）：列出**文件清单**（不自动解压逐个解析，避免 zip 炸弹/越界）。🟢
- PDF/Word：此处仅占位——真解析需 pdfminer/python-docx 等库，B7 在你环境接。🔴
- 图片/音视频/二进制：只存储 + 标注类型，**内容理解需多模态模型**，本服务不处理。🔴

安全：限制大小、zip 只读清单不解压、文件名清洗防路径穿越。
"""
from __future__ import annotations

import io
import os
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

MAX_BYTES = 20 * 1024 * 1024            # 单文件上限 20MB
TEXT_EXTS = {"txt", "md", "csv", "json", "log", "py", "js", "ts", "html", "css", "xml", "yaml", "yml"}
PARSE_PREVIEW = 8000                     # 解析出的文本预览上限（喂模型用，防 token 暴涨）


def _ext(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _safe_name(name: str) -> str:
    """清洗文件名：去路径分隔符，防穿越。"""
    return os.path.basename(name).replace("\\", "_").replace("/", "_") or "unnamed"


@dataclass
class UploadedFile:
    id: str
    filename: str
    ext: str
    size: int
    kind: str                 # text | archive | document | image | binary
    session_id: Optional[str]
    uploaded_at: float = field(default_factory=time.time)
    parsed_text: str = ""     # 文本类解析结果（喂模型）
    note: str = ""            # 解析说明（如"PDF 需 B7 解析"）

    def public(self) -> Dict[str, Any]:
        return {"id": self.id, "filename": self.filename, "ext": self.ext,
                "size": self.size, "kind": self.kind, "session_id": self.session_id,
                "uploaded_at": self.uploaded_at,
                "has_text": bool(self.parsed_text), "note": self.note}


def _classify(ext: str) -> str:
    if ext in TEXT_EXTS:
        return "text"
    if ext in ("zip",):
        return "archive"
    if ext in ("pdf", "doc", "docx"):
        return "document"
    if ext in ("png", "jpg", "jpeg", "gif", "webp", "bmp"):
        return "image"
    return "binary"


class FileService:
    def __init__(self) -> None:
        self._files: Dict[str, UploadedFile] = {}

    def ingest(self, filename: str, data: bytes,
               session_id: Optional[str] = None) -> Dict[str, Any]:
        """接收一个文件：校验 → 分类 → 按类型解析 → 存储。"""
        if len(data) > MAX_BYTES:
            raise ValueError(f"文件超过上限 {MAX_BYTES // 1024 // 1024}MB")
        name = _safe_name(filename)
        ext = _ext(name)
        kind = _classify(ext)
        fid = "f_" + uuid.uuid4().hex[:8]
        parsed, note = self._parse(kind, ext, data)
        f = UploadedFile(id=fid, filename=name, ext=ext, size=len(data),
                         kind=kind, session_id=session_id, parsed_text=parsed, note=note)
        self._files[fid] = f
        return f.public()

    def _parse(self, kind: str, ext: str, data: bytes) -> tuple:
        """按类型解析出可喂模型的文本 + 说明。"""
        if kind == "text":
            try:
                txt = data.decode("utf-8", errors="replace")
            except Exception:
                txt = data.decode("latin-1", errors="replace")
            preview = txt[:PARSE_PREVIEW]
            note = "" if len(txt) <= PARSE_PREVIEW else f"（已截断，原文 {len(txt)} 字）"
            return preview, note
        if kind == "archive" and ext == "zip":
            return self._zip_manifest(data)
        if kind == "document":
            return "", "PDF/Word 解析需在服务器接入（pdfminer/python-docx），当前仅存储。"
        if kind == "image":
            return "", "图片内容理解需多模态模型，当前仅存储。"
        return "", "二进制文件，仅存储，内容未解析。"

    def _zip_manifest(self, data: bytes) -> tuple:
        """压缩包：只列文件清单，不解压（防 zip 炸弹/越界）。"""
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()[:200]
                total = sum(i.file_size for i in z.infolist())
                lines = [f"压缩包含 {len(z.namelist())} 个文件（解压后约 {total // 1024}KB）："]
                lines += [f"  - {n}" for n in names]
                return "\n".join(lines), "压缩包仅列清单，未自动解压。"
        except zipfile.BadZipFile:
            return "", "无法读取的压缩包（损坏或非 zip）。"

    # ---------- 查询 ----------
    def get(self, file_id: str) -> Optional[UploadedFile]:
        return self._files.get(file_id)

    def list_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        return [f.public() for f in self._files.values() if f.session_id == session_id]

    def context_text(self, file_ids: List[str]) -> str:
        """把选中文件的解析文本拼成上下文块（喂模型）。无文本的只列文件名。"""
        blocks = []
        for fid in file_ids:
            f = self._files.get(fid)
            if not f:
                continue
            if f.parsed_text:
                blocks.append(f"【文件：{f.filename}】\n{f.parsed_text}")
            else:
                blocks.append(f"【文件：{f.filename}】（{f.note or '未解析'}）")
        return "\n\n".join(blocks)

    def delete(self, file_id: str) -> bool:
        return self._files.pop(file_id, None) is not None
