"""backend.settings — 环境驱动配置（B7）。

读环境变量决定每个后端用"真实"还是"内存/Mock"。没设的就回落内存版——
这样开发期(沙箱/本机无服务)照常跑，生产设上环境变量即切真实后端，**代码不改**。
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    # 模型（vLLM / LiteLLM，OpenAI 兼容）
    model_base_url: str = ""
    model_name: str = "vertical-70b"
    model_api_key: str = ""
    # 向量库（Chroma）
    chroma_host: str = ""
    chroma_port: int = 8000
    # Redis（配额原子扣减）
    redis_url: str = ""
    # Postgres（业务持久化）
    database_url: str = ""
    # 微信开放平台
    wechat_appid: str = ""
    wechat_secret: str = ""
    wechat_redirect_uri: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            model_base_url=os.environ.get("MODEL_BASE_URL", ""),
            model_name=os.environ.get("MODEL_NAME", "vertical-70b"),
            model_api_key=os.environ.get("MODEL_API_KEY", ""),
            chroma_host=os.environ.get("CHROMA_HOST", ""),
            chroma_port=int(os.environ.get("CHROMA_PORT", "8000")),
            redis_url=os.environ.get("REDIS_URL", ""),
            database_url=os.environ.get("DATABASE_URL", ""),
            wechat_appid=os.environ.get("WECHAT_APPID", ""),
            wechat_secret=os.environ.get("WECHAT_SECRET", ""),
            wechat_redirect_uri=os.environ.get("WECHAT_REDIRECT_URI", ""),
        )

    # 各后端是否启用真实实现
    @property
    def use_real_model(self) -> bool: return bool(self.model_base_url)
    @property
    def use_chroma(self) -> bool: return bool(self.chroma_host)
    @property
    def use_redis(self) -> bool: return bool(self.redis_url)
    @property
    def use_postgres(self) -> bool: return bool(self.database_url)
    @property
    def use_wechat(self) -> bool: return bool(self.wechat_appid and self.wechat_secret)
