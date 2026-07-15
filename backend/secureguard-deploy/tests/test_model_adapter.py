"""tests/test_model_adapter.py — 真实模型适配器（离线可测部分）。"""
import sys, os, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.model_adapter import parse_sse_line, build_request_body, build_model, OpenAICompatModel
from backend.model_service import ModelConfig


# ---------- SSE 解析（OpenAI 流式格式）----------
def test_parse_sse_token():
    line = 'data: {"choices":[{"delta":{"content":"你好"}}]}'
    assert parse_sse_line(line) == "你好"


def test_parse_sse_done_and_empty():
    assert parse_sse_line("data: [DONE]") is None
    assert parse_sse_line("") is None
    assert parse_sse_line(": comment") is None


def test_parse_sse_malformed():
    assert parse_sse_line("data: {bad json") is None
    assert parse_sse_line('data: {"choices":[]}') is None


def test_parse_sse_role_only_delta():
    # 首帧常只有 role 无 content
    assert parse_sse_line('data: {"choices":[{"delta":{"role":"assistant"}}]}') is None


# ---------- 请求体构造 ----------
def test_build_request_body():
    b = build_request_body("deepseek-chat", [{"role": "user", "content": "hi"}], stream=True, temperature=0.7)
    assert b["model"] == "deepseek-chat" and b["stream"] is True
    assert b["temperature"] == 0.7 and b["messages"][0]["content"] == "hi"


def test_build_request_omits_none_opts():
    b = build_request_body("m", [], stream=False)
    assert "temperature" not in b and "max_tokens" not in b


# ---------- 适配器构造与门控 ----------
def test_build_model_gates_on_config():
    # mock / 缺配置 → None（用内置）
    assert build_model(ModelConfig("builtin", "内置", "", "", "mock")) is None
    assert build_model(ModelConfig("x", "X", "", "sk-k", "deepseek-chat")) is None  # 缺 api_base
    assert build_model(ModelConfig("x", "X", "https://api.x.com/v1", "", "deepseek-chat")) is None  # 缺 key
    # 配置完整 → 真适配器
    m = build_model(ModelConfig("x", "X", "https://api.deepseek.com/v1", "sk-k", "deepseek-chat"))
    assert isinstance(m, OpenAICompatModel) and m.model == "deepseek-chat"


def test_adapter_messages_with_system():
    m = OpenAICompatModel("https://api.x.com/v1", "sk-k", "m", system="你是助手")
    msgs = m._messages("问题")
    assert msgs[0]["role"] == "system" and msgs[1]["content"] == "问题"


def test_adapter_url_normalizes_trailing_slash():
    m = OpenAICompatModel("https://api.x.com/v1/", "k", "m")
    assert m._url() == "https://api.x.com/v1/chat/completions"


# ---------- 注入 orchestrator：model_override 被使用（用假模型验证管线）----------
def test_model_override_used_in_orchestrator():
    """注入 model_override 后，MD 路径应调用它而非内置 MockModel。"""
    from backend.state import AppState
    from backend.chat_service import run_chat

    class FakeModel:
        called = False
        def generate(self, prompt, **kw):
            FakeModel.called = True
            return "<ASSESS>ok</ASSESS><ANSWER>这是真实模型的回答</ANSWER>"

    st = AppState()
    fake = FakeModel()
    async def go():
        ans = ""
        # 直接注入 ctx 的能力：用一个配置好的真实模型
        cfg = st.models.create("FakeLLM", "https://api.fake.com/v1", "sk-x", "fake-model")
        # monkeypatch build_model 返回我们的 fake
        import backend.model_adapter as ma
        orig = ma.build_model
        ma.build_model = lambda c: fake if c.model == "fake-model" else orig(c)
        try:
            async for ev in run_chat(st, "你好", agent_id="general", model=cfg["id"]):
                if ev["event"] == "delta":
                    ans += ev["text"]
        finally:
            ma.build_model = orig
        return ans
    ans = asyncio.run(go())
    assert FakeModel.called and "真实模型的回答" in ans


# ---------- 厂家清单 + 拉取（离线可测部分）----------
def test_providers_listed():
    from backend.model_adapter import list_providers
    ps = list_providers()
    ids = [p["id"] for p in ps]
    assert "deepseek" in ids and "openai" in ids and "custom" in ids
    ds = next(p for p in ps if p["id"] == "deepseek")
    assert ds["api_base"].endswith("/v1") and "deepseek-chat" in ds["models"]


def test_fetch_models_guards_missing():
    from backend.model_adapter import fetch_models
    r = fetch_models("", "sk-x")
    assert r["available"] is False and "缺少" in r["note"]
    r2 = fetch_models("https://api.x.com/v1", "")
    assert r2["available"] is False
