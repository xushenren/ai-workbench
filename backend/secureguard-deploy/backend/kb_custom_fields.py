"""
backend.kb_custom_fields — 自定义条目:人给条目名 → AI 判类型+建议值 → 人确认即定。

原则(与 0 幻觉/AI 副手一致):AI 只给"建议",人确认才算数。
AI 推断器可注入(生产走网关模型);默认含一个启发式桩,便于离线测。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class FieldType(str, Enum):
    BOOL = "bool"        # 是/否
    NUMBER = "number"    # 数量
    TEXT = "text"        # 文本
    DATE = "date"        # 日期


@dataclass
class FieldSuggestion:
    name: str
    suggested_type: FieldType
    suggested_value: str = ""
    rationale: str = ""          # AI 为何这么判(供人参考)


@dataclass
class FieldDef:
    """人确认后固定下来的字段定义。"""
    name: str
    type: FieldType
    confirmed: bool = True


# 推断器签名:(条目名, 可选样本内容) -> FieldSuggestion
Inferer = Callable[[str, str], FieldSuggestion]

_BOOL_HINT = ("是否", "有无", "能否", "可否", "合格", "通过", "防火", "防水", "达标")
_NUM_HINT = ("数量", "层数", "层高", "面积", "长度", "高度", "宽度", "厚度", "金额", "价格",
             "重量", "体积", "个数", "米", "数", "量")
_DATE_HINT = ("日期", "时间", "工期", "完工", "开工", "竣工")


def heuristic_inferer(name: str, sample: str = "") -> FieldSuggestion:
    """默认启发式:按条目名关键词猜类型。仅作建议,人可改。"""
    n = name.strip()
    if any(h in n for h in _BOOL_HINT):
        return FieldSuggestion(n, FieldType.BOOL, "否", f"名称含'是否/合格'类词,疑为是非项")
    if any(h in n for h in _DATE_HINT):
        return FieldSuggestion(n, FieldType.DATE, "", "名称含日期/工期类词")
    if any(h in n for h in _NUM_HINT):
        return FieldSuggestion(n, FieldType.NUMBER, "0", "名称含数量/尺寸类词,疑为数值")
    return FieldSuggestion(n, FieldType.TEXT, "", "未命中数值/是非/日期特征,暂按文本")


class CustomFieldService:
    def __init__(self, inferer: Inferer = heuristic_inferer) -> None:
        self.inferer = inferer
        self._defs: dict[str, FieldDef] = {}      # 已确认字段(name → def)

    def suggest(self, name: str, sample: str = "") -> FieldSuggestion:
        """AI 判类型+建议值(不落库,仅建议)。同名已确认则复用其类型。"""
        if name in self._defs:
            d = self._defs[name]
            return FieldSuggestion(name, d.type, "", "已确认字段,复用既定类型")
        return self.inferer(name, sample)

    def confirm(self, name: str, type: FieldType) -> FieldDef:
        """人确认(可改 AI 的建议),确认即固定。"""
        d = FieldDef(name=name, type=FieldType(type), confirmed=True)
        self._defs[name] = d
        return d

    def validate_value(self, name: str, value: str) -> tuple[bool, str]:
        """按已确认类型校验填入的值。"""
        d = self._defs.get(name)
        if not d:
            return False, "字段未确认"
        v = value.strip()
        if d.type == FieldType.BOOL:
            return (v in ("是", "否", "true", "false", "1", "0")), "应为 是/否"
        if d.type == FieldType.NUMBER:
            return (re.fullmatch(r"-?\d+(\.\d+)?", v) is not None), "应为数字"
        if d.type == FieldType.DATE:
            return (re.fullmatch(r"\d{4}[-/]\d{1,2}([-/]\d{1,2})?", v) is not None), "应为日期 YYYY-MM-DD"
        return True, ""

    def defs(self) -> list[FieldDef]:
        return list(self._defs.values())
