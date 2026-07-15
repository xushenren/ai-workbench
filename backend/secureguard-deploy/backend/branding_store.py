"""backend.branding_store — 白标品牌存储(落盘 DATA_DIR,可换 PG)。"""
from __future__ import annotations
import json, os, threading
from dataclasses import asdict, dataclass

DATA_DIR = os.getenv("DATA_DIR", "./data")
_PATH = os.path.join(DATA_DIR, "branding.json")
_lock = threading.Lock()

@dataclass
class Branding:
    platform_name: str = "AI 工作平台"     # 默认名,管理员可改
    logo_url: str = ""                      # 支持 http(s) 或 data:image/...;base64,
    favicon_url: str = ""
    brand_color: str = "#3b4cca"
    brand_color_dark: str = "#8ea2ff"
    lock_accent: bool = False               # True=员工不能改强调色(强品牌统一)
    login_tagline: str = ""
    def public(self) -> dict: return asdict(self)

def get_branding() -> Branding:
    try:
        with open(_PATH, encoding="utf-8") as f:
            return Branding(**json.load(f))
    except Exception:
        return Branding()

def set_branding(b: Branding) -> Branding:
    os.makedirs(DATA_DIR, exist_ok=True)
    with _lock, open(_PATH, "w", encoding="utf-8") as f:
        json.dump(asdict(b), f, ensure_ascii=False)
    return b
