"""backend.model_service — 模型配置（①）。

管理员维护"可用模型"列表：显示名 + API 地址 + API key + 模型标识 + 是否启用。
聊天时按 model_id 选用。纯 stdlib，可离线测。

诚实边界：本服务只管"配置与选择"。配置某模型后**真能否调通**取决于你填的
真实 API 地址/key，且回答质量由该模型决定——真实调用在 B7 接（此处仅存配置 +
mock 路由验证流程）。API key 返回给前端时**打码**，不明文下发。
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _mask(key: str) -> str:
    """API key 打码：只留末 4 位，避免明文回传前端。"""
    if not key:
        return ""
    return ("•" * 8) + key[-4:] if len(key) > 4 else "••••"


@dataclass
class ModelConfig:
    id: str
    name: str                 # 显示名，如 "DeepSeek-V3"
    api_base: str             # API 地址，如 https://api.deepseek.com/v1
    api_key: str              # 明文存后端，不回传前端
    model: str                # 模型标识，如 "deepseek-chat"
    enabled: bool = True
    created_at: float = field(default_factory=time.time)

    def public(self) -> Dict[str, Any]:
        """回传前端：key 打码。"""
        return {"id": self.id, "name": self.name, "api_base": self.api_base,
                "api_key_masked": _mask(self.api_key), "model": self.model,
                "enabled": self.enabled, "created_at": self.created_at}


class ModelService:
    def __init__(self, db_path: Optional[str] = None) -> None:
        self._models: Dict[str, ModelConfig] = {}
        self._db_path = db_path
        loaded = self._load()
        if not loaded:
            self._seed()
            self._save()

    def _load(self) -> bool:
        if not self._db_path:
            return False
        try:
            import json, os
            if os.path.exists(self._db_path):
                with open(self._db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._models = {k: ModelConfig(**v) for k, v in data.items()}
                return bool(self._models)
        except Exception:
            pass
        return False

    def _save(self) -> None:
        if not self._db_path:
            return
        try:
            import json, os
            from dataclasses import asdict
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
            with open(self._db_path, "w", encoding="utf-8") as f:
                json.dump({k: asdict(v) for k, v in self._models.items()}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _seed(self) -> None:
        # 预置一个"内置占位模型"（对应当前 MockModel），保证前端永远有可选项。
        self._models["builtin"] = ModelConfig(
            id="builtin", name="内置模型（占位）", api_base="", api_key="",
            model="mock", enabled=True)

    # ---------- 查询 ----------
    def list_models(self, include_disabled: bool = True) -> List[Dict[str, Any]]:
        ms = self._models.values()
        out = [m.public() for m in ms if include_disabled or m.enabled]
        return sorted(out, key=lambda m: m["created_at"])

    def list_selectable(self) -> List[Dict[str, Any]]:
        """聊天框下拉用：只列启用的。"""
        return self.list_models(include_disabled=False)

    def get(self, model_id: str) -> Optional[ModelConfig]:
        return self._models.get(model_id)

    def resolve(self, model_id: Optional[str]) -> ModelConfig:
        """选模型：给定 id 用之，否则回退到第一个启用的（或内置）。"""
        if model_id and model_id in self._models and self._models[model_id].enabled:
            return self._models[model_id]
        for m in self._models.values():
            if m.enabled:
                return m
        return self._models["builtin"]

    # ---------- 增删改（管理员） ----------
    def create(self, name: str, api_base: str, api_key: str, model: str,
               enabled: bool = True) -> Dict[str, Any]:
        if not name.strip() or not model.strip():
            raise ValueError("模型显示名与模型标识不能为空")
        mid = "m_" + uuid.uuid4().hex[:8]
        self._models[mid] = ModelConfig(id=mid, name=name.strip(),
            api_base=api_base.strip(), api_key=api_key.strip(),
            model=model.strip(), enabled=enabled)
        self._save()
        return self._models[mid].public()

    def update(self, model_id: str, **fields: Any) -> Dict[str, Any]:
        m = self._models.get(model_id)
        if not m:
            raise KeyError("模型不存在")
        if model_id == "builtin":
            raise ValueError("内置占位模型不可修改")
        for k in ("name", "api_base", "model", "enabled"):
            if k in fields and fields[k] is not None:
                setattr(m, k, fields[k])
        # api_key 仅在传了非空值时更新（避免前端回传打码值覆盖真 key）
        if fields.get("api_key"):
            m.api_key = fields["api_key"].strip()
        self._save()
        return m.public()

    def delete(self, model_id: str) -> bool:
        if model_id == "builtin":
            raise ValueError("内置占位模型不可删除")
        ok = self._models.pop(model_id, None) is not None
        if ok:
            self._save()
        return ok
