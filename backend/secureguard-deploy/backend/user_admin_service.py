"""backend.user_admin_service — 用户管理 + 部门申请（B-用户管理）。

解开"自助注册用户无部门→看不到任何部门资源"的死结：
  - admin 后台：列用户、改角色、分配部门、审批部门申请（权威路径）。
  - 用户：提交"加入某部门"的申请 → 进 admin 待审列表，**申请本身不授予任何权限**。

所有权限判定委托 permissions.can_manage_users（仅 admin）。纯 stdlib，可离线测。
"""
from __future__ import annotations

import secrets
from typing import Any, Dict, List, Optional

from secureguard.permissions import (
    User, Role, can_manage_users, can_set_role, can_delete_user, PermissionDenied,
)


class UserAdminService:
    def __init__(self, auth: Any) -> None:
        self.auth = auth
        self._requests: Dict[str, Dict[str, Any]] = {}  # req_id -> {user_id, dept_id, status}

    def _require_admin(self, caller: User) -> None:
        ok, reason = can_manage_users(caller)
        if not ok:
            raise PermissionDenied(reason)

    # ---------- admin/受限管理员：用户管理 ----------
    def list_users(self, caller: User) -> List[Dict[str, Any]]:
        self._require_admin(caller)
        return self.auth.list_users()

    def set_role(self, caller: User, user_id: str, role: str) -> Dict[str, Any]:
        self._require_admin(caller)
        if role not in {r.value for r in Role}:
            raise ValueError(f"未知角色: {role}")
        target = self.auth.get_user(user_id)
        if target is None:
            raise KeyError("用户不存在")
        # 护栏：受限管理员不能造 admin/受限管理员/审计员，不能碰 admin（防自我提权/绕过审计任命）
        ok, why = can_set_role(caller, target, Role(role))
        if not ok:
            raise PermissionDenied(why)
        self.auth.set_role(user_id, role)
        return {"user_id": user_id, "role": role}

    def assign_department(self, caller: User, user_id: str, dept_id: Optional[str]) -> Dict[str, Any]:
        self._require_admin(caller)
        if not self.auth.set_department(user_id, dept_id):
            raise KeyError("用户不存在")
        return {"user_id": user_id, "dept_id": dept_id}

    def delete_user(self, caller: User, user_id: str) -> Dict[str, Any]:
        self._require_admin(caller)
        target = self.auth.get_user(user_id)
        if target is None:
            raise KeyError("用户不存在")
        # 护栏：受限管理员不能删 admin/受限管理员/审计员；admin 不能删 admin
        ok, why = can_delete_user(caller, target)
        if not ok:
            raise PermissionDenied(why)
        self.auth.delete_user(user_id)
        return {"deleted": user_id}

    # ---------- 用户：申请部门（不授权，仅入待审） ----------
    def request_department(self, caller: User, dept_id: str) -> Dict[str, Any]:
        req_id = "req_" + secrets.token_hex(4)
        self._requests[req_id] = {"id": req_id, "user_id": caller.id, "dept_id": dept_id, "status": "pending"}
        return self._requests[req_id]

    # ---------- admin：审批申请 ----------
    def list_requests(self, caller: User, only_pending: bool = True) -> List[Dict[str, Any]]:
        self._require_admin(caller)
        reqs = list(self._requests.values())
        return [r for r in reqs if r["status"] == "pending"] if only_pending else reqs

    def approve_request(self, caller: User, req_id: str) -> Dict[str, Any]:
        self._require_admin(caller)
        req = self._requests.get(req_id)
        if not req:
            raise KeyError("申请不存在")
        # 审批通过才真正写部门（权威授权点）
        self.auth.set_department(req["user_id"], req["dept_id"])
        req["status"] = "approved"
        return req

    def reject_request(self, caller: User, req_id: str) -> Dict[str, Any]:
        self._require_admin(caller)
        req = self._requests.get(req_id)
        if not req:
            raise KeyError("申请不存在")
        req["status"] = "rejected"
        return req
