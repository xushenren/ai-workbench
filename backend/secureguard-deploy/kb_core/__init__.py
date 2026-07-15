"""kb_core — 知识库三池 + 置信晋升(建在 org_core 之上)。"""
from .models import EntryStatus, Inspection, KBEntry, Pool
from .repository import KBRepo, SqliteKBRepo
from .service import KBConflict, KBService
from .inspect import inspect

__all__ = [
    "Pool", "EntryStatus", "KBEntry", "Inspection",
    "KBRepo", "SqliteKBRepo", "KBService", "KBConflict", "inspect",
    "confidence_label", "annotate_sources",
]
__version__ = "0.1.0"

# 置信标签(给答复/grounding 用):池 → 面向用户的可信度提示
_LABEL = {
    Pool.PUBLIC_HIGH: ("高置信", "已由专家审定"),
    Pool.PUBLIC_LOW: ("低置信", "用户共享 · 待核实"),
    Pool.PRIVATE: ("私有", "仅你可见"),
}


def confidence_label(entry: "KBEntry") -> tuple[str, str]:
    return _LABEL.get(entry.pool, ("未知", ""))


def annotate_sources(entries: list["KBEntry"]) -> dict:
    """把检索结果按置信分组,供答复分段标注:哪些高置信、哪些低置信(需核实)。"""
    high = [e for e in entries if e.pool == Pool.PUBLIC_HIGH]
    low = [e for e in entries if e.pool == Pool.PUBLIC_LOW]
    private = [e for e in entries if e.pool == Pool.PRIVATE]
    return {
        "high": [e.title for e in high],
        "low": [e.title for e in low],
        "private": [e.title for e in private],
        "risk_hint": ("部分内容来自低置信/未核实来源,请谨慎采用。" if low else ""),
    }
