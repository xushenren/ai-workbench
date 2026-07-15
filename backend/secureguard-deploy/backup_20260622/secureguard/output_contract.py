"""secureguard.output_contract — 弱模型输出契约校验器（执行层）。

提示词让弱模型吐出结构（见 prompts/weak-model-scaffold.md），本模块负责**强制**：
解析不出必填段、有未降级的 [G] 猜测、自检表报了未标注断言、置信度过低 →
fail-closed 判 BLOCK/ASK，交由上层用 P-RETRY 打回重做，而**绝不放行**。

这就是"弱模型也能可靠"的真正落点——可靠性来自这道关，不来自模型自觉。
纯标准库，可离线测试。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .types import Token

# 必填段（FALSIFY 条件性必填，可为 N/A）
REQUIRED_SECTIONS = ["ASSESS", "CLAIMS", "OBJECTIONS", "SELFCHECK", "ANSWER"]


def _extract(text: str, name: str) -> Optional[str]:
    """容错抽取 <NAME>...</NAME>，大小写/空格无所谓。"""
    m = re.search(rf"<\s*{name}\s*>(.*?)<\s*/\s*{name}\s*>", text,
                  re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else None


@dataclass
class ContractResult:
    token: Token
    reasons: List[str] = field(default_factory=list)
    missing_sections: List[str] = field(default_factory=list)
    ask_items: List[str] = field(default_factory=list)
    unsourced_claims: List[str] = field(default_factory=list)
    confidence: Optional[float] = None
    focus: str = ""              # 给 P-RETRY 的重点提示

    def to_dict(self) -> Dict:
        return {
            "token": self.token.value,
            "reasons": self.reasons,
            "missing_sections": self.missing_sections,
            "ask_items": self.ask_items,
            "unsourced_claims": self.unsourced_claims,
            "confidence": self.confidence,
            "focus": self.focus,
        }


class OutputContract:
    """校验弱模型的结构化输出。fail-closed：不合格一律不放行。"""

    def __init__(self, min_confidence: float = 4.0) -> None:
        self.min_confidence = min_confidence

    def validate(self, text: str) -> ContractResult:
        reasons: List[str] = []

        # 1) 必填段齐全（缺段 = fail-closed BLOCK 打回）
        missing = [s for s in REQUIRED_SECTIONS if _extract(text, s) is None]
        if missing:
            return ContractResult(
                Token.BLOCK,
                reasons=[f"缺失必填段：{', '.join(missing)}"],
                missing_sections=missing,
                focus="补齐缺失段并按结构重发",
            )

        assess = _extract(text, "ASSESS") or ""
        claims = _extract(text, "CLAIMS") or ""
        selfcheck = _extract(text, "SELFCHECK") or ""

        # 2) 入口门：有 ASK 项 → 暂停问用户
        ask_items = [ln.strip() for ln in assess.splitlines()
                     if re.search(r"\bASK\b", ln, re.IGNORECASE)]
        if ask_items:
            return ContractResult(
                Token.ASK,
                reasons=["存在需澄清的不可逆/承重信息(ASK)"],
                ask_items=ask_items,
            )

        # 3) 反幻觉：未降级的 [G] 猜测，或漏标来源 → BLOCK 打回
        unsourced: List[str] = []
        claim_lines = [ln.strip() for ln in claims.splitlines() if ln.strip()
                       and ln.strip().lower() not in ("none", "n/a")]
        hedge = re.compile(r"需核实|待核实|不确定|可能|存疑|待验证", re.IGNORECASE)
        for ln in claim_lines:
            has_tag = re.search(r"\[(S|M|G)\]", ln, re.IGNORECASE)
            if not has_tag:
                unsourced.append(ln)
                continue
            # [G] 猜测必须降级；未降级即违约
            if re.search(r"\[G\]", ln, re.IGNORECASE) and not hedge.search(ln):
                unsourced.append(ln)
        if unsourced:
            reasons.append(f"有 {len(unsourced)} 条断言漏标来源或为未降级的猜测")

        # 4) 自检表：未标注断言计数 + 置信度
        conf = self._parse_confidence(selfcheck)
        unflagged = self._parse_unflagged_count(selfcheck)
        if unflagged and unflagged > 0:
            reasons.append(f"自检承认有 {unflagged} 条关键结论未降级/未标注")

        # 决策：有反幻觉违约或自检自承问题 → BLOCK 打回
        if unsourced or (unflagged and unflagged > 0):
            return ContractResult(
                Token.BLOCK, reasons=reasons, unsourced_claims=unsourced,
                confidence=conf, focus="给每条 [M]/[G] 断言加来源或降级为'需核实'",
            )

        # 5) 置信度过低 → ASK（路由到二次核实/人工，而非直接给低质量答案）
        if conf is not None and conf < self.min_confidence:
            return ContractResult(
                Token.ASK, reasons=[f"自评置信度 {conf} < {self.min_confidence}，需核实"],
                confidence=conf, focus="先走检索/人工核实再作答",
            )

        return ContractResult(Token.PASS, reasons=["契约通过"], confidence=conf)

    @staticmethod
    def _parse_confidence(selfcheck: str) -> Optional[float]:
        m = re.search(r"置信度\D{0,6}(\d+(?:\.\d+)?)", selfcheck)
        if not m:
            m = re.search(r"\b(\d+(?:\.\d+)?)\s*/\s*10", selfcheck)
        return float(m.group(1)) if m else None

    @staticmethod
    def _parse_unflagged_count(selfcheck: str) -> Optional[int]:
        """读自检第 2 题"有几条未降级"的数字。"""
        for ln in selfcheck.splitlines():
            if re.search(r"未标注|未降级|没标|没降级", ln):
                # 先剥掉行首题号（如 "2. " / "2、"），避免把题号当成数量
                body = re.sub(r"^\s*\d+\s*[.、)]\s*", "", ln)
                m = re.search(r"(\d+)\s*条", body) or re.search(r"(\d+)", body)
                if m:
                    return int(m.group(1))
        return None
