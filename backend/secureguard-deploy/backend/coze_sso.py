"""backend.coze_sso — 平台 ↔ Coze 单点登录(同机同源)。

原理:你平台登录后,后端用"确定性 email+密码"替该用户在 Coze 注册+登录,
取回 Coze 的 session_key,种到浏览器(同域)。之后进内嵌的 Coze 模块,
Coze 中间件读到 session_key 即认证通过——用户无需再登一次。

Coze 接口(已对齐其源码):
  POST /api/passport/web/email/login/        form: email, password   → Set-Cookie session_key
  POST /api/passport/web/email/register/v2/  form: email, password   → Set-Cookie session_key
HTTP 层可注入(http_post),便于离线测;默认用 stdlib urllib(无新依赖)。
"""
from __future__ import annotations

import hashlib
import hmac
import urllib.parse
import urllib.request
from typing import Callable, Optional, Tuple

SESSION_COOKIE = "session_key"


def _default_http_post(url: str, form: dict) -> Tuple[int, str, Optional[str]]:
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            sk = _extract_session(resp.headers.get_all("Set-Cookie") or [])
            return resp.status, body, sk
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="ignore"), None


def _extract_session(set_cookies) -> Optional[str]:
    for c in set_cookies:
        for part in c.split(";"):
            part = part.strip()
            if part.startswith(SESSION_COOKIE + "="):
                return part[len(SESSION_COOKIE) + 1:]
    return None


class CozeSSO:
    def __init__(self, base_url: str, shared_secret: str,
                 email_domain: str = "coze.local",
                 http_post: Callable[[str, dict], Tuple[int, str, Optional[str]]] = _default_http_post) -> None:
        self.base = base_url.rstrip("/")           # 如 http://127.0.0.1:8888
        self.secret = shared_secret.encode()
        self.email_domain = email_domain
        self.http_post = http_post

    def email_for(self, user_id: str) -> str:
        return f"u{user_id}@{self.email_domain}"

    def password_for(self, user_id: str) -> str:
        # 确定性密码:平台密钥派生,不可被外部猜出
        return "Cz" + hmac.new(self.secret, str(user_id).encode(), hashlib.sha256).hexdigest()[:22]

    def _login(self, email: str, pwd: str) -> Optional[str]:
        st, _, sk = self.http_post(self.base + "/api/passport/web/email/login/",
                                   {"email": email, "password": pwd})
        return sk if (st == 200 and sk) else None

    def _register(self, email: str, pwd: str) -> Optional[str]:
        st, _, sk = self.http_post(self.base + "/api/passport/web/email/register/v2/",
                                   {"email": email, "password": pwd})
        return sk if (st == 200 and sk) else None

    def mint_session(self, user_id: str) -> Optional[str]:
        """取该用户的 Coze session_key:先登录,失败则注册(注册即登录)。"""
        email, pwd = self.email_for(user_id), self.password_for(user_id)
        sk = self._login(email, pwd)
        if sk:
            return sk
        sk = self._register(email, pwd)      # 首次:注册并拿到 session
        if sk:
            return sk
        return self._login(email, pwd)       # 注册成功但未返回cookie时再登一次
