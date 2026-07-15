"""backend.auth — 认证与授权（B2，框架无关核心）。

包含：
  - AuthService：内存用户表 + 会话令牌。密码用 pbkdf2 哈希存储，**绝不存明文**。
  - authorize_role：纯函数角色门，配合 permissions.py 的细粒度判定。
  - 微信 OAuth：给出桩 + 接入说明，需真实 AppID/Secret，**沙箱不可测，标注清楚**。

不依赖 FastAPI，可纯 stdlib 测试。FastAPI 的依赖注入在 deps/app 里薄封装。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from typing import Dict, List, Optional, Tuple

from secureguard.permissions import User, Role

_PBKDF2_ROUNDS = 100_000


class AuthService:
    """内存认证服务。生产把 _users/_sessions 换成 Postgres/Redis（B7），接口不变。"""

    def __init__(self, session_ttl: int = 3600) -> None:
        self._users: Dict[str, Dict] = {}      # phone -> record
        self._sessions: Dict[str, Tuple[str, float]] = {}  # token -> (user_id, expiry)
        self.session_ttl = session_ttl
        self._seed()

    # ---------- 密码哈希（pbkdf2，加盐，不存明文） ----------
    @staticmethod
    def _hash(password: str, salt: bytes) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS).hex()

    def register(self, phone: str, password: str, role: str,
                 dept_id: Optional[str] = None, user_id: Optional[str] = None) -> str:
        salt = os.urandom(16)
        uid = user_id or ("u_" + secrets.token_hex(4))
        self._users[phone] = {
            "id": uid, "phone": phone, "salt": salt,
            "hash": self._hash(password, salt), "role": role, "dept_id": dept_id,
        }
        return uid

    # ---------- 登录 / 会话 ----------
    def login(self, phone: str, password: str) -> Tuple[Optional[str], str]:
        """返回 (token, message)。失败 token 为 None。"""
        rec = self._users.get(phone)
        if not rec:
            return None, "用户不存在"
        # 恒定时间比较，防时序侧信道
        if not hmac.compare_digest(rec["hash"], self._hash(password, rec["salt"])):
            return None, "手机号或密码错误"
        token = secrets.token_urlsafe(24)
        self._sessions[token] = (rec["id"], time.time() + self.session_ttl)
        return token, "登录成功"

    def resolve(self, token: Optional[str]) -> Optional[User]:
        """令牌 → User。无效/过期返回 None。"""
        if not token:
            return None
        sess = self._sessions.get(token)
        if not sess:
            return None
        uid, exp = sess
        if time.time() > exp:
            self._sessions.pop(token, None)
            return None
        rec = next((r for r in self._users.values() if r["id"] == uid), None)
        if not rec:
            return None
        return User(id=rec["id"], role=Role(rec["role"]), dept_id=rec["dept_id"])

    def logout(self, token: str) -> None:
        self._sessions.pop(token, None)

    def get_user(self, user_id: str) -> Optional[User]:
        """按 id 取 User（供配额管理等需要 target 身份的场景）。"""
        rec = next((r for r in self._users.values() if r["id"] == user_id), None)
        if not rec:
            return None
        return User(id=rec["id"], role=Role(rec["role"]), dept_id=rec["dept_id"])

    # ---------- 用户管理（供 admin 后台；改动即时对后续请求生效，因 resolve 实时读记录） ----------
    def list_users(self) -> List[Dict]:
        return [{"id": r["id"], "phone": r["phone"], "role": r["role"], "dept_id": r["dept_id"]}
                for r in self._users.values()]

    def _rec_by_id(self, user_id: str) -> Optional[Dict]:
        return next((r for r in self._users.values() if r["id"] == user_id), None)

    def set_role(self, user_id: str, role: str) -> bool:
        rec = self._rec_by_id(user_id)
        if not rec or role not in {r.value for r in Role}:
            return False
        rec["role"] = role
        return True

    def set_department(self, user_id: str, dept_id: Optional[str]) -> bool:
        rec = self._rec_by_id(user_id)
        if not rec:
            return False
        rec["dept_id"] = dept_id
        return True

    def delete_user(self, user_id: str) -> bool:
        phone = next((p for p, r in self._users.items() if r["id"] == user_id), None)
        if phone is None:
            return False
        del self._users[phone]
        return True

    def register_self(self, phone: str, password: str) -> Tuple[Optional[str], str]:
        """自助注册。**强制 role=user**（绝不让客户端选 admin/developer，防提权）。

        成功返回 (token, msg) 直接登录态；失败 token 为 None。
        """
        import re as _re
        if not _re.fullmatch(r"1[3-9]\d{9}", phone or ""):
            return None, "手机号格式不正确"
        if len(password or "") < 6:
            return None, "密码至少 6 位"
        if phone in self._users:
            return None, "该手机号已注册"
        self.register(phone, password, role="user", dept_id=None)  # 角色写死 user
        return self.login(phone, password)  # 注册即登录

    def _seed(self) -> None:
        """开发期种子账号（生产删除）。密码仅示例。"""
        self.register("13800000000", "admin123", "admin", None, "u_admin")
        self.register("13800000001", "dev123", "developer", "d1", "u_dev")
        self.register("13800000002", "da123", "department_admin", "d1", "u_da")
        self.register("13800000003", "user123", "user", "d1", "u_user")
        self.register("13800000004", "audit123", "auditor", None, "u_auditor")  # 受控审计员
        self.register("13800000005", "radmin123", "restricted_admin", None, "u_radmin")  # 受限管理员


# ====================================================================== #
# 角色门（纯函数，配合 permissions.py 的细粒度判定）
# ====================================================================== #
def authorize_role(user: Optional[User], allowed: List[Role]) -> Tuple[bool, str]:
    """粗粒度角色门：user 角色是否在 allowed 内。细粒度归属判定走 permissions.py。"""
    if user is None:
        return False, "未认证"
    if user.role in allowed:
        return True, "ok"
    return False, f"需要角色 {[r.value for r in allowed]}，当前 {user.role.value}"


# ====================================================================== #
# 微信扫码登录（桩）—— 需真实 AppID/Secret，沙箱不可测，真机接入
# ====================================================================== #
def wechat_qr() -> Dict[str, str]:  # pragma: no cover - 需真实微信开放平台
    """返回扫码登录所需的二维码 URL。

    真实实现：用 WECHAT_APPID 拼 https://open.weixin.qq.com/connect/qrconnect
    带 redirect_uri / state，前端渲染二维码。此处仅桩。
    """
    appid = os.environ.get("WECHAT_APPID")
    if not appid:
        return {"status": "not_configured", "message": "未配置 WECHAT_APPID，微信登录不可用"}
    state = secrets.token_urlsafe(12)
    redirect = os.environ.get("WECHAT_REDIRECT_URI", "")
    url = (f"https://open.weixin.qq.com/connect/qrconnect?appid={appid}"
           f"&redirect_uri={redirect}&response_type=code&scope=snsapi_login&state={state}")
    return {"status": "ok", "qr_url": url, "state": state}


def wechat_callback(code: str, auth: AuthService) -> Tuple[Optional[str], str]:  # pragma: no cover
    """微信回调：code 换 access_token+openid，再换/建本地账号发会话 token。

    真实实现需向 https://api.weixin.qq.com/sns/oauth2/access_token 发请求（需联网+密钥）。
    沙箱无网络无密钥，此处仅说明流程，不可运行。
    """
    raise NotImplementedError("微信 OAuth 需真实 AppID/Secret 与外网，真机接入")
