"""backend.adapters.vllm_model — 真实模型后端（vLLM / LiteLLM，OpenAI 兼容）。

⚠️ 未在沙箱测试：需真实 model endpoint + 网络。接口与 secureguard.MockModel 一致
（generate / generate_stream），所以工厂里 swap 是配置级。httpx 懒加载，无依赖时类仍可导入，
只在实例化/调用时报清晰错误，便于接口形状测试。
"""
from __future__ import annotations

from typing import Iterator, List, Dict, Any


class VLLMModel:
    """OpenAI 兼容 chat/completions 后端。MockModel 的真实替身。"""

    def __init__(self, base_url: str, model: str = "vertical-70b", api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def _client(self):
        try:
            import httpx  # 懒加载：无 httpx 时仅在此报错
        except Exception as e:  # pragma: no cover
            raise RuntimeError("VLLMModel 需要 httpx：pip install httpx") from e
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        return httpx.Client(base_url=self.base_url, headers=headers, timeout=60.0)

    def _messages(self, prompt: str) -> List[Dict[str, str]]:
        return [{"role": "user", "content": prompt}]

    def generate(self, prompt: str, **kwargs: Any) -> str:  # pragma: no cover - 需真实服务
        with self._client() as c:
            r = c.post("/v1/chat/completions", json={
                "model": self.model, "messages": self._messages(prompt),
                "stream": False, **kwargs,
            })
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

    def generate_stream(self, prompt: str, **kwargs: Any) -> Iterator[str]:  # pragma: no cover
        """逐 token 流式（SSE）。orchestrator.stream 在 B7 可切到这里，实现真·流式。"""
        import json
        with self._client() as c:
            with c.stream("POST", "/v1/chat/completions", json={
                "model": self.model, "messages": self._messages(prompt),
                "stream": True, **kwargs,
            }) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[len("data:"):].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        delta = json.loads(payload)["choices"][0]["delta"].get("content", "")
                    except Exception:
                        delta = ""
                    if delta:
                        yield delta
