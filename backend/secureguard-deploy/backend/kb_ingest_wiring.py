"""backend.kb_ingest_wiring — 把解析器/映射表/OCR/配置接到一起,供端点调用。"""
from __future__ import annotations
import json, os, subprocess, tempfile
from .kb_parser_registry import ParserRegistry
from .kb_batch_ingest import IngestConfig
from .kb_doc_parsers import get_parser

DATA_DIR = os.getenv("DATA_DIR", "./data")
_CFG_PATH = os.path.join(DATA_DIR, "ingest_config.json")

REGISTRY = ParserRegistry()           # 进程内;如需持久化映射,可落 DATA_DIR

def load_config() -> IngestConfig:
    try:
        with open(_CFG_PATH, encoding="utf-8") as f:
            return IngestConfig(**json.load(f))
    except Exception:
        return IngestConfig()

def save_config(cfg: IngestConfig) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg.__dict__, f, ensure_ascii=False)

# ---- OCR 工厂(PaddleOCR;管理后台开关控制是否启用)----
_ocr = None
def make_ocr_fn(lang: str = "ch"):
    """返回 bytes->str 的 OCR 函数;懒加载 PaddleOCR。装库在服务器。"""
    global _ocr
    def ocr_fn(img_bytes: bytes) -> str:
        global _ocr
        if _ocr is None:
            try:
                from paddleocr import PaddleOCR
            except ImportError:
                raise RuntimeError("需安装 paddleocr + paddlepaddle(龙虾部署)")
            _ocr = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
        import numpy as np  # noqa
        from PIL import Image
        import io as _io
        img = Image.open(_io.BytesIO(img_bytes)).convert("RGB")
        res = _ocr.ocr(np.array(img), cls=True)
        lines = []
        for page in (res or []):
            for line in (page or []):
                lines.append(line[1][0])
        return "\n".join(lines)
    return ocr_fn

def make_extract_fn(cfg: IngestConfig):
    ocr_fn = make_ocr_fn(cfg.ocr_lang) if cfg.ocr_enabled else None
    def extract(name, data, registry, cfg):
        ext = os.path.splitext(name)[1].lower()
        m = registry.resolve(ext)
        if m.external_cmd:                       # 专有格式走外部工具
            return _run_external(m.external_cmd, data, ext)
        return get_parser(m.parser)(data, ocr_fn=(ocr_fn if cfg.ocr_enabled else None))
    return extract

def _run_external(cmd_tpl: str, data: bytes, ext: str) -> str:
    with tempfile.TemporaryDirectory() as d:
        inp = os.path.join(d, "in" + ext); out = os.path.join(d, "out.txt")
        with open(inp, "wb") as f: f.write(data)
        cmd = cmd_tpl.replace("{input}", inp).replace("{output}", out)
        subprocess.run(cmd, shell=True, timeout=120, check=False)
        if os.path.exists(out):
            return open(out, encoding="utf-8", errors="replace").read()
        return ""
