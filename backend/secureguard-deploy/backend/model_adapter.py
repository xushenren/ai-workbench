"""backend.model_adapter — 真实模型适配器（OpenAI 兼容流式）。

覆盖绝大多数模型：DeepSeek / 通义 / Kimi / OpenAI / 本地 vLLM 等，
因为它们都兼容 OpenAI 的 POST {api_base}/chat/completions（SSE 流式）。

诚实边界：
- 真实 HTTP 往返需要联网 + 真实 api_key，本沙箱断网测不了 → 标 🔴。
- 离线可测的部分：请求体构造、SSE 行解析（把 data: {...} 解析成 token）、降级。
- 用 stdlib urllib，不引第三方依赖（生产可换 httpx 提升并发，接口不变）。

接口：
- generate(prompt) -> str        同步全量（兜底 / 非流式场景）
- stream(prompt) -> Iterator[str] 逐 token（流式）
失败时不抛断全局：返回明确错误文本 / 空迭代，由上层降级。
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Iterator, List, Dict, Any, Optional

from secureguard.l2_reasoning import ModelBackend


def parse_sse_line(line: str) -> Optional[str]:
    """解析一行 SSE，返回该行的增量 token（无则 None）。

    OpenAI 流式格式：每行 `data: {json}`，json.choices[0].delta.content 是增量。
    结束标志 `data: [DONE]`。可离线测。
    """
    line = line.strip()
    if not line or not line.startswith("data:"):
        return None
    payload = line[len("data:"):].strip()
    if payload == "[DONE]":
        return None
    try:
        obj = json.loads(payload)
        return obj.get("choices", [{}])[0].get("delta", {}).get("content")
    except (json.JSONDecodeError, IndexError, KeyError, TypeError):
        return None


def build_request_body(model: str, messages: List[Dict[str, str]],
                       stream: bool, **opts: Any) -> Dict[str, Any]:
    """构造 OpenAI 兼容请求体。可离线测。"""
    body = {"model": model, "messages": messages, "stream": stream}
    for k in ("temperature", "max_tokens", "top_p"):
        if k in opts and opts[k] is not None:
            body[k] = opts[k]
    return body


class OpenAICompatModel(ModelBackend):
    """OpenAI 兼容模型适配器。与 MockModel 同接口（generate），并加 stream。"""

    def __init__(self, api_base: str, api_key: str, model: str,
                 timeout: int = 60, system: Optional[str] = None) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.system = system

    def _messages(self, prompt: str) -> List[Dict[str, str]]:
        msgs: List[Dict[str, str]] = []
        if self.system:
            msgs.append({"role": "system", "content": self.system})
        msgs.append({"role": "user", "content": prompt})
        return msgs

    def _url(self) -> str:
        return f"{self.api_base}/chat/completions"

    def _headers(self) -> Dict[str, str]:
        return {"Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"}

    # ---------- 同步全量（🔴 真实往返需联网）----------
    def generate(self, prompt: str, **kwargs) -> str:  # pragma: no cover - 需联网
        body = build_request_body(self.model, self._messages(prompt), stream=False, **kwargs)
        req = urllib.request.Request(self._url(), data=json.dumps(body).encode(),
                                     headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode())
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except urllib.error.HTTPError as e:
            return f"[模型调用失败 HTTP {e.code}：{e.reason}]"
        except Exception as e:
            return f"[模型调用失败：{e}]"

    # ---------- 流式逐 token（🔴 真实往返需联网）----------
    def stream(self, prompt: str, **kwargs) -> Iterator[str]:  # pragma: no cover - 需联网
        body = build_request_body(self.model, self._messages(prompt), stream=True, **kwargs)
        req = urllib.request.Request(self._url(), data=json.dumps(body).encode(),
                                     headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for raw in resp:
                    tok = parse_sse_line(raw.decode("utf-8", errors="replace"))
                    if tok:
                        yield tok
        except urllib.error.HTTPError as e:
            yield f"[模型调用失败 HTTP {e.code}：{e.reason}]"
        except Exception as e:
            yield f"[模型调用失败：{e}]"


def build_model(cfg: Any) -> Optional[ModelBackend]:
    """按模型配置构造适配器。cfg.model=='mock' 或缺 api_base/key → 返回 None（用内置）。"""
    model_id = getattr(cfg, "model", None)
    api_base = getattr(cfg, "api_base", "")
    api_key = getattr(cfg, "api_key", "")
    if not model_id or model_id == "mock" or not api_base or not api_key:
        return None
    return OpenAICompatModel(api_base=api_base, api_key=api_key, model=model_id)


# ---------- 厂家预置清单（选厂家自动带出 api_base + 常见模型名）----------
# api_base 与模型名按已知填写；各厂家可能更新，前端允许改/拉取/手填兜底。
PROVIDERS: List[Dict[str, Any]] = [
    {"id": "deepseek", "name": "DeepSeek 深度求索",
     "api_base": "https://api.deepseek.com/v1",
     "models": ["deepseek-chat", "deepseek-reasoner"]},
    {"id": "qwen", "name": "通义千问（阿里）",
     "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
     "models": ["qwen-max", "qwen-plus", "qwen-turbo"]},
    {"id": "moonshot", "name": "Kimi 月之暗面",
     "api_base": "https://api.moonshot.cn/v1",
     "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]},
    {"id": "zhipu", "name": "智谱 GLM",
     "api_base": "https://open.bigmodel.cn/api/paas/v4",
     "models": ["glm-4-plus", "glm-4", "glm-4-flash"]},
    {"id": "openai", "name": "OpenAI",
     "api_base": "https://api.openai.com/v1",
     "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]},
    {"id": "minimax", "name": "MiniMax",
     "api_base": "https://api.minimax.chat/v1",
     "models": ["abab6.5s-chat"]},
    {"id": "baichuan", "name": "百川",
     "api_base": "https://api.baichuan-ai.com/v1",
     "models": ["Baichuan4", "Baichuan3-Turbo"]},
    {"id": "siliconflow", "name": "硅基流动 SiliconFlow",
     "api_base": "https://api.siliconflow.cn/v1",
     "models": ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct"]},
    {"id": "custom", "name": "本地 / 自定义（手填地址）",
     "api_base": "", "models": []},
]


def list_providers() -> List[Dict[str, Any]]:
    return PROVIDERS


def fetch_models(api_base: str, api_key: str, timeout: int = 15) -> Dict[str, Any]:
    """用 key 拉取该账号可用模型列表（OpenAI 兼容 GET {api_base}/models）。

    🔴 真实联网请求，本沙箱断网测不了。返回 {available, models, note}。
    拉取失败（不支持/网络/鉴权）→ available=False，由前端回退到厂家预置模型名手选。
    """
    if not api_base or not api_key:
        return {"available": False, "models": [], "note": "缺少 API 地址或 Key"}
    url = f"{api_base.rstrip('/')}/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"}, method="GET")
    try:  # pragma: no cover - 需联网
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
        return {"available": True, "models": sorted(ids),
                "note": "" if ids else "该接口未返回模型列表，请手填模型标识"}
    except urllib.error.HTTPError as e:  # pragma: no cover
        return {"available": False, "models": [],
                "note": f"拉取失败 HTTP {e.code}（key 无效或该厂家不支持列表接口），请手填"}
    except Exception as e:  # pragma: no cover
        return {"available": False, "models": [], "note": f"拉取失败（{e}），请手填模型标识"}
