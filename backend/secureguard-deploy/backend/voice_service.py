"""backend.voice_service — 语音能力（③④⑤）。

诚实边界（务必读）：本服务交付的是**适配器接口 + 离线 mock + 配置**。
真模型都在你的服务器/联网环境接，我沙箱里跑不了：
- ③ ASR（语音转文字）：接口 + mock。真模型如 Whisper 🔴 你接。
- ④ MOSS-TTS-Nano（复旦 OpenMOSS，本地 CPU 推理，带音色克隆）：TTS 适配器 🔴 你部署后接。
- ⑤ edge-tts（微软在线 TTS，可选声音/语速/音高）：适配器 + 参数 🔴 需后端联网调微软。

设计：ASR/TTS 各定义统一接口，按 backend 配置切换（mock / whisper / moss / edge）。
未接真模型时返回 available=False，**绝不假装合成/识别成功**。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# edge-tts 常用声音（前端下拉用；真正合成需后端接 edge-tts）
EDGE_VOICES = [
    {"id": "zh-CN-XiaoxiaoNeural", "name": "晓晓（女声·温柔）"},
    {"id": "zh-CN-YunxiNeural", "name": "云希（男声·沉稳）"},
    {"id": "zh-CN-XiaoyiNeural", "name": "晓伊（女声·活泼）"},
    {"id": "zh-CN-YunjianNeural", "name": "云健（男声·浑厚）"},
    {"id": "en-US-AriaNeural", "name": "Aria（英语·女声）"},
]


class ASRService:
    """语音识别：音频 → 文字。"""

    def __init__(self, backend: str = "mock") -> None:
        self.backend = backend           # mock | whisper（🔴 你接）

    def transcribe(self, audio: bytes, language: str = "zh") -> Dict[str, Any]:
        if self.backend == "mock":
            # 离线占位：不假装识别真实内容，明确标注。
            return {"available": True, "backend": "mock", "text": "",
                    "note": "ASR 未接入真实模型（如 Whisper）。当前为占位，未真正识别。",
                    "duration_bytes": len(audio)}
        # 🔴 B7：whisper 等真实模型在你服务器接。
        #   例：调用本地 whisper 服务 POST 音频 → 返回 text。
        return {"available": False, "backend": self.backend, "text": "",
                "note": f"ASR 后端 {self.backend} 未接入。"}


class TTSService:
    """语音合成：文字 → 音频。支持 moss（本地）/ edge（微软）/ mock。"""

    def __init__(self, backend: str = "mock") -> None:
        self.backend = backend           # mock | moss | edge（🔴 你接）

    def list_voices(self) -> List[Dict[str, str]]:
        if self.backend == "edge":
            return EDGE_VOICES
        if self.backend == "moss":
            # MOSS-TTS-Nano 支持音色克隆；此处给占位音色，真音色由你的部署提供。
            return [{"id": "moss-default", "name": "MOSS 默认音色"},
                    {"id": "moss-clone", "name": "MOSS 克隆音色（需上传样本）"}]
        return [{"id": "mock", "name": "占位音色"}]

    def synthesize(self, text: str, voice: Optional[str] = None,
                   rate: float = 1.0, pitch: float = 1.0) -> Dict[str, Any]:
        """文字 → 音频。rate 语速、pitch 音高（edge/moss 支持）。

        返回 audio_b64 时前端可直接播放；mock/未接时 available=False，不假装合成。
        """
        if not text.strip():
            return {"available": False, "error": "empty_text"}
        if self.backend == "mock":
            return {"available": False, "backend": "mock", "audio_b64": "",
                    "note": "TTS 未接入真实引擎（MOSS-TTS / edge-tts）。当前为占位，未真正合成。",
                    "voice": voice, "rate": rate, "pitch": pitch}
        # 🔴 B7：
        #   moss → 调本地 MOSS-TTS-Nano 服务（你部署的 708MB 模型），传 text/voice → 返回音频。
        #   edge → 调 edge-tts（需后端联网），传 text/voice/rate/pitch → 返回音频 mp3。
        return {"available": False, "backend": self.backend, "audio_b64": "",
                "note": f"TTS 后端 {self.backend} 未接入。"}


class VoiceService:
    """语音总入口：聚合 ASR + TTS，按环境变量配置后端。"""

    def __init__(self) -> None:
        self.asr = ASRService(backend=os.environ.get("ASR_BACKEND", "mock"))
        self.tts = TTSService(backend=os.environ.get("TTS_BACKEND", "mock"))

    def config(self) -> Dict[str, Any]:
        """前端查询：当前语音能力状态 + 可选音色。"""
        return {
            "asr": {"backend": self.asr.backend, "available": self.asr.backend != "mock"},
            "tts": {"backend": self.tts.backend, "available": self.tts.backend != "mock",
                    "voices": self.tts.list_voices()},
        }
