"""tests/test_output_contract.py — 弱模型输出契约校验器单测。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from secureguard.output_contract import OutputContract
from secureguard.types import Token

C = OutputContract()

GOOD = """
<ASSESS>none</ASSESS>
<CLAIMS>
- [S] 幂等性指同一操作多次结果一致（doc_1）
- [M] 需核实：该接口超时默认 30s（记忆，可能过时）
</CLAIMS>
<FALSIFY>N/A</FALSIFY>
<OBJECTIONS>用户没提并发场景，我按单线程假设作答。</OBJECTIONS>
<SELFCHECK>
1. no
2. 0 条未标注
3. no
4. 最可能错在超时默认值
5. 置信度 8，扣分在记忆类数据
</SELFCHECK>
<ANSWER>幂等性的解释…</ANSWER>
"""


def test_good_output_passes():
    r = C.validate(GOOD)
    assert r.token == Token.PASS and r.confidence == 8.0


def test_missing_section_blocks():
    txt = GOOD.replace("<SELFCHECK>", "<X>").replace("</SELFCHECK>", "</X>")
    r = C.validate(txt)
    assert r.token == Token.BLOCK and "SELFCHECK" in r.missing_sections


def test_ask_item_pauses():
    txt = GOOD.replace("<ASSESS>none</ASSESS>",
                       "<ASSESS>- 目标环境是不是生产？ASK</ASSESS>")
    r = C.validate(txt)
    assert r.token == Token.ASK and r.ask_items


def test_unhedged_guess_blocks():
    txt = GOOD.replace("- [M] 需核实：该接口超时默认 30s（记忆，可能过时）",
                       "- [G] 该接口超时默认就是 30s")  # 猜测且未降级
    r = C.validate(txt)
    assert r.token == Token.BLOCK and r.unsourced_claims


def test_untagged_claim_blocks():
    txt = GOOD.replace("- [S] 幂等性指同一操作多次结果一致（doc_1）",
                       "- 幂等性一定不会有副作用")  # 漏标来源
    r = C.validate(txt)
    assert r.token == Token.BLOCK


def test_low_confidence_routes_to_ask():
    txt = GOOD.replace("置信度 8，扣分在记忆类数据", "置信度 2，证据不足")
    r = C.validate(txt)
    assert r.token == Token.ASK and r.confidence == 2.0


def test_selfcheck_admits_unflagged_blocks():
    txt = GOOD.replace("2. 0 条未标注", "2. 有 3 条未标注")
    r = C.validate(txt)
    assert r.token == Token.BLOCK


def test_malformed_fails_closed_not_open():
    r = C.validate("这是一段没有任何结构的自由文本。")
    assert r.token == Token.BLOCK  # 解析不出 → 打回，绝不放行
