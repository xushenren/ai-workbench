"""secureguard.l3_output_guard — L3 输出守卫（模型输出后、用户看到前）。

职责：
  1. 幻觉信号检测（不确定性表述、无来源断言、绝对化措辞、未核对日期）。
  2. 敏感信息脱敏（>=12 种凭据格式）。
  3. 引用覆盖检查（要求 require_citation 时）。
  4. 输出质量评分（OutputQuality）。

脱敏采取“先检测后替换”，脱敏后的文本才是允许返回给用户的文本。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

_FLAGS = re.IGNORECASE | re.UNICODE


@dataclass
class OutputQuality:
    """输出质量打分（0-1 区间，overall_pass 综合判定）。"""

    hallucination_risk: float = 0.0   # 幻觉信号密度（越低越好）
    citation_coverage: float = 0.0    # 引用覆盖（越高越好）
    sanitization_applied: bool = False
    sensitive_hits: int = 0
    overall_pass: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


class OutputGuard:
    """L3 输出守卫。纯标准库，无第三方依赖。"""

    # 幻觉信号：命中不代表一定是幻觉，但提示需要核对/降权。
    HALLUCINATION_SIGNALS: List[Tuple[str, str]] = [
        (r"\b(I\s+think|I\s+believe|probably|maybe|likely|possibly|might\s+be)\b", "不确定性表述"),
        (r"\b(according\s+to\s+my\s+(training|knowledge|understanding))\b", "无来源断言"),
        (r"\b(as\s+far\s+as\s+I\s+know|to\s+the\s+best\s+of\s+my\s+knowledge)\b", "模糊边界"),
        (r"\b(all|every|always|never|none|only|guaranteed|definitely)\b", "绝对化表述"),
        (r"\b\d{4}-\d{2}-\d{2}\b", "日期断言(需核对)"),
        (r"(我认为|我觉得|大概|也许|应该是|可能)", "中文不确定表述"),
    ]

    # >=12 种敏感/凭据格式。注意顺序：更具体的放前面。
    SENSITIVE_PATTERNS: List[Tuple[str, str]] = [
        (r"sk-ant-[A-Za-z0-9_\-]{20,}", "[ANTHROPIC_KEY_REDACTED]"),
        (r"sk-[A-Za-z0-9]{20,}", "[OPENAI_KEY_REDACTED]"),
        (r"ghp_[A-Za-z0-9]{30,}", "[GITHUB_TOKEN_REDACTED]"),
        (r"github_pat_[A-Za-z0-9_]{20,}", "[GITHUB_PAT_REDACTED]"),
        (r"gho_[A-Za-z0-9]{30,}", "[GITHUB_OAUTH_REDACTED]"),
        (r"AIza[0-9A-Za-z_\-]{30,}", "[GOOGLE_KEY_REDACTED]"),
        (r"ya29\.[0-9A-Za-z_\-]{20,}", "[GOOGLE_OAUTH_REDACTED]"),
        (r"AKIA[0-9A-Z]{16}", "[AWS_ACCESS_KEY_REDACTED]"),
        (r"xox[baprs]-[0-9A-Za-z\-]{10,}", "[SLACK_TOKEN_REDACTED]"),
        (r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}", "[JWT_REDACTED]"),
        (r"-----BEGIN\s+(RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE\s+KEY-----", "[PRIVATE_KEY_BLOCK_REDACTED]"),
        (r"\b(postgres|mysql|mongodb|redis|amqp)://[^\s:@]+:[^\s:@]+@[^\s/]+", "[DB_CONN_REDACTED]"),
        (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN_REDACTED]"),
        (r"(?i)(password|passwd|secret|token|api[_\s\-]*key)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]"),
    ]

    def __init__(self) -> None:
        self._hall = [(re.compile(p, _FLAGS), label) for p, label in self.HALLUCINATION_SIGNALS]
        self._sens = [(re.compile(p, _FLAGS), repl) for p, repl in self.SENSITIVE_PATTERNS]

    def check(self, output: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """检查 + 脱敏。返回 issues、脱敏文本与质量评分。"""
        context = context or {}
        issues: List[Dict[str, str]] = []

        # 1) 幻觉信号
        hall_hits = 0
        for pat, label in self._hall:
            if pat.search(output):
                hall_hits += 1
                issues.append({"type": "hallucination_signal", "label": label})

        # 2) 引用覆盖
        citations = re.findall(r"\[doc_\d+\]", output)
        if context.get("require_citation") and not citations:
            issues.append({"type": "missing_citation", "label": "要求引用但缺少来源标注"})

        # 3) 敏感信息脱敏（先检测后替换）
        sanitized = output
        sensitive_hits = 0
        for pat, repl in self._sens:
            if pat.search(sanitized):
                sensitive_hits += 1
                issues.append({"type": "sensitive_data", "label": "检测到敏感信息"})
                sanitized = pat.sub(repl, sanitized)

        # 4) 质量评分
        # 简单代理：句子数估算用于归一化幻觉密度。
        approx_sentences = max(1, len(re.findall(r"[。.!?！？\n]", output)) or 1)
        quality = OutputQuality(
            hallucination_risk=round(min(1.0, hall_hits / approx_sentences), 3),
            citation_coverage=round(min(1.0, len(citations) / approx_sentences), 3),
            sanitization_applied=sensitive_hits > 0,
            sensitive_hits=sensitive_hits,
        )
        # 通过条件：无敏感泄漏，且（不要求引用 或 已有引用）
        quality.overall_pass = (
            sensitive_hits == 0
            and (not context.get("require_citation") or bool(citations))
        )

        return {
            "safe": sensitive_hits == 0,
            "issues": issues,
            "sanitized_output": sanitized,
            "citations": citations,
            "quality": quality.to_dict(),
            "overall_pass": quality.overall_pass,
        }
