"""backend.deps — FastAPI 认证/授权依赖（B2 的 Web 绑定层）。

import-guarded：无 fastapi 时本模块仍可导入。真正的认证逻辑在 auth.py（已测），
这里只是把它接成 FastAPI 的 Depends。
"""
from __future__ import annotations

from typing import List, Optional

from secureguard.permissions import User, Role
from .auth import authorize_role

try:
    from fastapi import Header, HTTPException, Depends  # type: ignore
    _FASTAPI = True
except Exception:  # pragma: no cover
    _FASTAPI = False


def _token_from_header(authorization: Optional[str]) -> Optional[str]:
    """从 'Authorization: Bearer xxx' 取出令牌。"""
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return authorization  # 容忍直接传裸 token


if _FASTAPI:  # pragma: no cover - 需 fastapi
    from .app import state

    async def get_caller(authorization: Optional[str] = Header(default=None)) -> User:
        """解析当前用户；未认证抛 401。"""
        user = state.auth.resolve(_token_from_header(authorization))
        if user is None:
            raise HTTPException(status_code=401, detail="未认证或会话已过期")
        return user

    async def get_caller_optional(authorization: Optional[str] = Header(default=None)) -> Optional[User]:
        """可选认证：拿不到也不报错（如匿名可用的对话）。"""
        return state.auth.resolve(_token_from_header(authorization))

    def require_role(*allowed: Role):
        """依赖工厂：要求调用者属于指定角色之一。"""
        async def _dep(user: User = Depends(get_caller)) -> User:
            ok, reason = authorize_role(user, list(allowed))
            if not ok:
                raise HTTPException(status_code=403, detail=reason)
            return user
        return _dep
