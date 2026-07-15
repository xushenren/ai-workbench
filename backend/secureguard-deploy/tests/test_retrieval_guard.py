"""tests/test_retrieval_guard.py — 检索版权护栏单测。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from secureguard.retrieval_guard import RetrievalGuard
from secureguard.l2_reasoning import Doc

g = RetrievalGuard()

SRC = [
    Doc("doc_1",
        "The committee concluded that the new policy would reduce emissions "
        "by twenty percent over the next decade while creating thousands of jobs "
        "in the renewable energy sector across the region.",
        {"trust_score": 0.9}),
    Doc("doc_2", "幂等性指同一操作执行多次与执行一次产生相同的副作用与结果。", {"trust_score": 0.8}),
]


def test_short_quote_passes():
    out = 'The report says the policy will "reduce emissions by twenty percent" overall.'
    rep = g.check(out, SRC)
    assert rep.ok, rep.to_dict()


def test_long_quote_flagged():
    # 22 词逐字引用，超过 15 词上限
    out = ('Analysts noted: "the new policy would reduce emissions by twenty percent '
           'over the next decade while creating thousands of jobs in the renewable energy sector".')
    rep = g.check(out, SRC)
    assert any(v.kind == "quote_too_long" for v in rep.violations)


def test_unquoted_reproduction_flagged():
    # 大段未加引号逐字搬运
    out = ("Here is the summary. the new policy would reduce emissions by twenty percent "
           "over the next decade while creating thousands of jobs in the renewable energy sector.")
    rep = g.check(out, SRC)
    assert any(v.kind == "unquoted_reproduction" for v in rep.violations)


def test_multi_quote_same_source_flagged():
    g1 = RetrievalGuard(max_quote_words=50)  # 放宽长度，专测条数
    out = ('First "the new policy would reduce emissions" and also '
           '"creating thousands of jobs in the renewable energy sector".')
    rep = g1.check(out, SRC)
    assert any(v.kind == "multi_quote_same_source" for v in rep.violations)


def test_cjk_long_quote_flagged():
    g2 = RetrievalGuard(max_quote_cjk_chars=10)
    out = '原文称「幂等性指同一操作执行多次与执行一次产生相同的副作用与结果」如上。'
    rep = g2.check(out, SRC)
    assert any(v.kind == "quote_too_long" for v in rep.violations)


def test_clean_paraphrase_passes():
    out = "据 doc_1，该政策预计十年内显著降低排放并带动可再生能源就业 [doc_1]。"
    rep = g.check(out, SRC)
    assert rep.ok, rep.to_dict()
