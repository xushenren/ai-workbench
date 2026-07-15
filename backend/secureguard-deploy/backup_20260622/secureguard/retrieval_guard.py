"""secureguard.retrieval_guard — 检索/版权护栏（把"输出内容约束"编码为可执行检查）。

回答咨询 #3：版权硬限制不是"安全红线"（红线是 action 级的"能不能做"），
而是"输出格式/内容约束"（output 级的"产出长什么样"）。因此它建模为
**输出侧 DomainGuard**：拿模型输出 + 检索到的源文档，逐条核对：

  1. 单条引用 ≤ N 词（拉丁 15 词 / 中日韩 30 字，可配置）
  2. 单源至多 1 条逐字引用（按"逐字命中某源"归属）
  3. 禁止未加引号的逐字复制（近似复述/结构搬运）—— 用最长连续逐字 token 串检测
  4. 禁止复述完整作品 —— 输出对单一源的逐字覆盖率超阈值即判定

判定 verdict：发现违规 → 返回 BLOCK_OR_REWRITE，并给出每条违规的定位，
供上层选择"重写为转述"或拒绝。纯标准库，无第三方依赖，可离线测试。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# 引号形态：直引号 / 弯引号 / 中文引号 / 书名号
_QUOTE_SPANS = re.compile(
    r"\"([^\"]{1,400})\""        # "..."
    r"|“([^”]{1,400})”"          # “...”
    r"|「([^」]{1,400})」"        # 「...」
    r"|『([^』]{1,400})』"        # 『...』
    r"|《([^》]{1,400})》",       # 《...》
)

_CJK = r"\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af"


def _is_cjk_dominant(text: str) -> bool:
    cjk = len(re.findall(f"[{_CJK}]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return cjk >= latin


def _tokenize(text: str) -> List[str]:
    """拉丁词整体成 token，中日韩按单字成 token；用于逐字重叠比对。"""
    return re.findall(rf"[A-Za-z0-9]+|[{_CJK}]", text.lower())


def _quote_length(span: str) -> Tuple[str, int]:
    """返回 (计量方式, 长度)。中日韩按字数，拉丁按词数。"""
    if _is_cjk_dominant(span):
        return "cjk_chars", len(re.findall(f"[{_CJK}]", span))
    return "latin_words", len(span.split())


def _longest_verbatim_run(out_tokens: List[str], src_tokens: List[str]) -> int:
    """输出与单源之间最长连续逐字 token 串长度（经典 DP，规模小足够）。"""
    if not out_tokens or not src_tokens:
        return 0
    prev = [0] * (len(src_tokens) + 1)
    best = 0
    for i in range(1, len(out_tokens) + 1):
        cur = [0] * (len(src_tokens) + 1)
        oi = out_tokens[i - 1]
        for j in range(1, len(src_tokens) + 1):
            if oi == src_tokens[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


@dataclass
class RetrievalViolation:
    kind: str                 # quote_too_long / multi_quote_same_source / unquoted_reproduction / full_work
    detail: str
    evidence: str = ""
    source_id: str = ""


@dataclass
class RetrievalReport:
    ok: bool
    violations: List[RetrievalViolation] = field(default_factory=list)
    quotes_found: int = 0
    max_verbatim_run: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "violations": [v.__dict__ for v in self.violations],
            "quotes_found": self.quotes_found,
            "max_verbatim_run": self.max_verbatim_run,
        }


class RetrievalGuard:
    """检索版权护栏。check() 接收输出与源文档，逐条核对版权约束。"""

    tier = "DOMAIN_GUARD"

    def __init__(
        self,
        max_quote_words: int = 15,        # 单条拉丁引用词上限
        max_quote_cjk_chars: int = 30,    # 单条中日韩引用字上限
        max_quotes_per_source: int = 1,   # 单源逐字引用条数上限
        unquoted_run_threshold: int = 12,  # 未加引号逐字串 token 阈值
        full_work_coverage: float = 0.5,  # 对单源逐字覆盖率上限
    ) -> None:
        self.max_quote_words = max_quote_words
        self.max_quote_cjk_chars = max_quote_cjk_chars
        self.max_quotes_per_source = max_quotes_per_source
        self.unquoted_run_threshold = unquoted_run_threshold
        self.full_work_coverage = full_work_coverage

    @staticmethod
    def _extract_quotes(text: str) -> List[str]:
        spans = []
        for m in _QUOTE_SPANS.finditer(text):
            span = next((g for g in m.groups() if g), None)
            if span:
                spans.append(span.strip())
        return spans

    def check(self, output: str, sources: List[Any]) -> RetrievalReport:
        """sources: 可迭代，元素需有 .id 与 .content（如 l2_reasoning.Doc）。"""
        violations: List[RetrievalViolation] = []
        quotes = self._extract_quotes(output)

        # --- 规则 1：单条引用长度 ---
        for q in quotes:
            mode, length = _quote_length(q)
            limit = self.max_quote_cjk_chars if mode == "cjk_chars" else self.max_quote_words
            if length > limit:
                violations.append(RetrievalViolation(
                    kind="quote_too_long",
                    detail=f"引用{length}{'字' if mode=='cjk_chars' else '词'} > 上限{limit}",
                    evidence=q[:60],
                ))

        # --- 规则 2：单源逐字引用条数（按引用是否逐字命中某源归属）---
        src_quote_count: Dict[str, int] = {}
        for q in quotes:
            q_tokens = _tokenize(q)
            for s in sources:
                run = _longest_verbatim_run(q_tokens, _tokenize(s.content))
                # 引用绝大部分逐字来自该源 → 归属为对该源的一条引用
                if q_tokens and run >= max(1, int(len(q_tokens) * 0.8)):
                    src_quote_count[s.id] = src_quote_count.get(s.id, 0) + 1
        for sid, cnt in src_quote_count.items():
            if cnt > self.max_quotes_per_source:
                violations.append(RetrievalViolation(
                    kind="multi_quote_same_source",
                    detail=f"对源 {sid} 有 {cnt} 条逐字引用 > 上限 {self.max_quotes_per_source}",
                    source_id=sid,
                ))

        # --- 规则 3/4：未加引号逐字复制 + 完整作品复述 ---
        out_tokens = _tokenize(output)
        # 去掉引号内内容后的"正文 token"，用于检测未加引号的逐字搬运
        stripped = _QUOTE_SPANS.sub(" ", output)
        body_tokens = _tokenize(stripped)
        max_run_overall = 0
        for s in sources:
            s_tokens = _tokenize(s.content)
            # 未加引号逐字串
            body_run = _longest_verbatim_run(body_tokens, s_tokens)
            max_run_overall = max(max_run_overall, body_run)
            if body_run >= self.unquoted_run_threshold:
                violations.append(RetrievalViolation(
                    kind="unquoted_reproduction",
                    detail=f"未加引号逐字串达 {body_run} token（阈值 {self.unquoted_run_threshold}）",
                    source_id=s.id,
                ))
            # 完整作品复述：输出对该源的逐字覆盖率
            full_run = _longest_verbatim_run(out_tokens, s_tokens)
            if s_tokens and full_run / len(s_tokens) >= self.full_work_coverage:
                violations.append(RetrievalViolation(
                    kind="full_work",
                    detail=f"对源 {s.id} 逐字覆盖率 {full_run/len(s_tokens):.0%} ≥ {self.full_work_coverage:.0%}",
                    source_id=s.id,
                ))

        return RetrievalReport(
            ok=not violations,
            violations=violations,
            quotes_found=len(quotes),
            max_verbatim_run=max_run_overall,
        )
