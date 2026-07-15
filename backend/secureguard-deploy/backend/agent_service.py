"""backend.agent_service — 智能体 CRUD + 发布状态机（B3，框架无关核心）。

桥接两套字段：
  - RBAC 字段（permissions.Agent）：owner_id / visibility / status / dept_id —— 决定谁能创建/见/批。
  - 业务字段：name / domain / scope / tier / description ... —— 决定怎么用。

所有权限判定**全部委托 permissions.py**（create_agent/submit/approve/reject/can_use_agent），
本服务只负责存储与字段桥接。纯 stdlib，可离线测。
"""
from __future__ import annotations

import secrets
from typing import Any, Dict, List, Optional

from secureguard.permissions import (
    User, Agent as RBACAgent, Visibility, AgentStatus, Role,
    create_agent, submit_for_review, approve, reject, can_use_agent,
)

# 匿名用户（未登录）视图：用于 list_for 时只放行"已发布的公共"智能体。
_ANON = User(id="__anon__", role=Role.USER, dept_id=None)


def _biz_defaults() -> Dict[str, Any]:
    return {"description": "", "domain": "general", "scope": "open", "tier": "tier1",
            "icon": "🤖", "tools_count": 0, "skills_count": 0, "kb_count": 0,
            "free_quota_tokens": 10000, "kb_ids": []}


class AgentService:
    """智能体存储 + 生命周期。生产把 _agents 换 Postgres（B7），接口不变。"""

    def __init__(self, seed: bool = True, db_path: Optional[str] = None) -> None:
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._db_path = db_path
        loaded = self._load()
        if seed and not loaded:
            self._seed()
            self._save()

    # ---------- 持久化（JSON 落盘，重启不丢）----------
    def _load(self) -> bool:
        if not self._db_path:
            return False
        try:
            import json, os
            if os.path.exists(self._db_path):
                with open(self._db_path, "r", encoding="utf-8") as f:
                    self._agents = json.load(f)
                return bool(self._agents)
        except Exception:
            pass
        return False

    def _save(self) -> None:
        if not self._db_path:
            return
        try:
            import json, os
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
            with open(self._db_path, "w", encoding="utf-8") as f:
                json.dump(self._agents, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- RBAC 视图桥接 ----------
    @staticmethod
    def _rbac(rec: Dict[str, Any]) -> RBACAgent:
        return RBACAgent(
            id=rec["id"], owner_id=rec["owner_id"],
            visibility=Visibility(rec["visibility"]),
            status=AgentStatus(rec["status"]), dept_id=rec.get("dept_id"),
        )

    # ---------- 创建 ----------
    def create(self, caller: User, payload: Dict[str, Any]) -> Dict[str, Any]:
        """创建智能体。私有直发 published；多人可见进 draft。越权抛 PermissionDenied。"""
        vis = Visibility(payload.get("visibility", "private"))
        agent_id = payload.get("id") or ("ag_" + secrets.token_hex(4))
        # 权限 + 状态全由 permissions.create_agent 决定（含"普通 user 不能建多人可见"）
        rbac = create_agent(caller, agent_id, vis, payload.get("dept_id"))
        rec = {
            **_biz_defaults(),
            "id": rbac.id, "owner_id": rbac.owner_id,
            "visibility": rbac.visibility.value, "status": rbac.status.value,
            "dept_id": rbac.dept_id,
            "name": payload.get("name", "未命名智能体"),
        }
        for k in ("description", "domain", "scope", "tier", "icon",
                  "tools_count", "skills_count", "kb_count", "free_quota_tokens", "kb_ids"):
            if k in payload:
                rec[k] = payload[k]
        self._agents[rec["id"]] = rec
        self._save()
        return rec

    # ---------- 发布状态机（委托 permissions） ----------
    def _transition(self, caller: User, agent_id: str, fn) -> Dict[str, Any]:
        rec = self._require(agent_id)
        a = self._rbac(rec)
        fn(caller, a)                 # 越权/状态非法时抛 PermissionDenied
        rec["status"] = a.status.value
        self._save()
        return rec

    def submit(self, caller: User, agent_id: str) -> Dict[str, Any]:
        return self._transition(caller, agent_id, submit_for_review)

    def approve(self, caller: User, agent_id: str) -> Dict[str, Any]:
        return self._transition(caller, agent_id, approve)

    def reject(self, caller: User, agent_id: str) -> Dict[str, Any]:
        return self._transition(caller, agent_id, reject)

    # ---------- 查询 ----------
    def get(self, agent_id: Optional[str]) -> Optional[Dict[str, Any]]:
        return self._agents.get(agent_id or "")

    def _require(self, agent_id: str) -> Dict[str, Any]:
        rec = self._agents.get(agent_id)
        if not rec:
            raise KeyError(f"智能体不存在: {agent_id}")
        return rec

    def list_for(self, caller: Optional[User]) -> List[Dict[str, Any]]:
        """按 permissions.can_use_agent 过滤。匿名只见已发布公共。"""
        user = caller or _ANON
        return [r for r in self._agents.values() if can_use_agent(user, self._rbac(r))[0]]

    # ---------- 删除 ----------
    def delete_by_name(self, caller: User, name: str) -> bool:
        """按名删除（覆盖导入用）。仅 owner 或 admin 可删。"""
        rv = getattr(getattr(caller, "role", None), "value", "user")
        for aid, rec in list(self._agents.items()):
            if rec.get("name") == name:
                if rec.get("owner_id") != getattr(caller, "id", None) and rv != "admin":
                    from secureguard.permissions import PermissionDenied
                    raise PermissionDenied("仅创建者或管理员可覆盖同名智能体")
                del self._agents[aid]
                self._save()
                return True
        return False

    # ---------- 种子（内置三个公共智能体，已发布） ----------
    def _seed(self) -> None:
        base = [
            {"id": "general", "name": "通用助手", "icon": "🤖", "domain": "general",
             "scope": "open", "description": "日常问答与写作，可联网，适合非敏感开放任务。",
             "tools_count": 3, "skills_count": 1, "kb_count": 1, "free_quota_tokens": 20000},
            {"id": "electromechanical", "name": "机电安装助手", "icon": "🏗️",
             "domain": "electromechanical", "scope": "domain_only",
             "description": "建筑机电安装专业助手，回答锚定 GB50243 等标准，自带引用合规校验。",
             "tools_count": 3, "skills_count": 3, "kb_count": 2, "free_quota_tokens": 10000, "kb_ids": []},
            {"id": "code", "name": "代码助手", "icon": "💻", "domain": "software",
             "scope": "domain_only",
             "description": "代码生成与审查，强调状态变更三件套与可逆性，敏感任务强制本地算力。",
             "tools_count": 4, "skills_count": 2, "kb_count": 1, "free_quota_tokens": 15000},
        ]
        for b in base:
            self._agents[b["id"]] = {
                **_biz_defaults(), **b,
                "owner_id": "u_admin", "visibility": "public",
                "status": "published", "dept_id": None,
            }
