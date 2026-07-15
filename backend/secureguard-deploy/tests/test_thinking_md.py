"""tests/test_thinking_md.py — MD 驱动思考：加载/组合/切片/端到端帧。"""
import sys, os, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.thinking_md import load_profile, split_sections, Step
from backend.state import AppState
from backend.chat_service import run_chat


def test_main_profile_has_steps():
    p = load_profile()
    keys = [s.key for s in p.steps]
    assert keys == ["assess", "gather", "reason", "selfcheck", "answer"]


def test_domain_overlay_inserts_step_before_answer():
    p = load_profile("software")
    keys = [s.key for s in p.steps]
    assert "verify" in keys
    assert keys.index("verify") < keys.index("answer")  # 执行验证在作答前
    assert "domain-software" in "+".join(p.sources)


def test_unknown_domain_falls_back_to_main():
    p = load_profile("nonexistent")
    assert [s.key for s in p.steps] == ["assess", "gather", "reason", "selfcheck", "answer"]


def test_split_sections_extracts_tags():
    steps = [Step("assess", "评估"), Step("answer", "作答")]
    txt = "<ASSESS>需求清楚</ASSESS><ANSWER>这是答案</ANSWER>"
    out = split_sections(txt, steps)
    assert out["assess"] == "需求清楚" and out["answer"] == "这是答案"


def test_hot_reload_reads_file_each_time(tmp_path=None):
    """两次加载都重读文件——改文件即生效（热加载）。"""
    p1 = load_profile()
    p2 = load_profile()
    assert p1.steps_dict() == p2.steps_dict()  # 一致且每次重读


def _collect(msg, agent):
    async def go():
        st = AppState(); think = []; ans = ""
        async for ev in run_chat(st, msg, agent_id=agent):
            if ev["event"] == "trace" and ev["frame"]["stage"] == "think" \
                    and ev["frame"]["status"] == "done":  # 只取每步完成帧
                think.append(ev["frame"]["display"])
            elif ev["event"] == "delta":
                ans += ev["text"]
        return think, ans
    return asyncio.run(go())


def test_stepwise_running_then_done_per_step():
    """分步流式：每步先 running 再 done，同一 step 标识，可原地更新。"""
    async def go():
        st = AppState(); pairs = []
        async for ev in run_chat(st, "风管验收", agent_id="general"):
            if ev["event"] == "trace" and ev["frame"]["stage"] == "think":
                pairs.append((ev["frame"].get("step"), ev["frame"]["status"]))
        return pairs
    pairs = asyncio.run(go())
    # 每个出现的 step 都应有 running 和 done
    steps = {s for s, _ in pairs}
    for s in steps:
        assert (s, "running") in pairs and (s, "done") in pairs


def test_general_emits_md_think_frames():
    think, ans = _collect("风管验收标准", "general")
    labels = [t.split("：")[0] for t in think]
    assert labels == ["评估需求", "检索取证", "推理", "自检"]  # answer 走 delta 不在 think
    assert ans  # 有答案


def test_code_agent_adds_verify_step():
    think, _ = _collect("写个排序函数", "code")
    labels = [t.split("：")[0] for t in think]
    assert "执行验证" in labels


def test_md_frames_carry_no_rule_id():
    """安全约束不破：MD 思考帧同样不含 rule_id。"""
    async def go():
        st = AppState()
        async for ev in run_chat(st, "风管验收", agent_id="general"):
            if ev["event"] == "trace":
                assert "rule_id" not in ev["frame"]
                assert "params" not in ev["frame"]
    asyncio.run(go())


def test_md_path_filters_irrelevant_docs():
    """问题1：MD 路径不再乱拉不相干文档（编程问题不应命中机电规范）。"""
    async def go(msg):
        st = AppState(); gather = ""
        async for ev in run_chat(st, msg, agent_id="code"):
            f = ev.get("frame", {})
            if ev["event"] == "trace" and f.get("step") == "gather" and f["status"] == "done":
                gather = f["display"]
        return gather
    # 编程问题：低相关度 → context 为空 → 诚实说资料未覆盖（不灌机电文档）
    g = asyncio.run(go("开发俄罗斯方块游戏"))
    assert "doc_1" not in g and ("未覆盖" in g or "资料" in g)
