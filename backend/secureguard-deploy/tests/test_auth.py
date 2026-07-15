"""tests/test_auth.py — B2 认证与授权单测（纯 stdlib）。"""
import sys, os, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.auth import AuthService, authorize_role, wechat_qr, wechat_callback
from secureguard.permissions import Role


def test_login_success_returns_token():
    a = AuthService()
    token, msg = a.login("13800000000", "admin123")
    assert token and msg == "登录成功"


def test_login_wrong_password_fails():
    a = AuthService()
    token, msg = a.login("13800000000", "wrong")
    assert token is None and "密码" in msg


def test_login_unknown_user_fails():
    a = AuthService()
    token, _ = a.login("19900000000", "x")
    assert token is None


def test_password_never_stored_plaintext():
    a = AuthService()
    rec = a._users["13800000000"]
    assert "admin123" not in str(rec)            # 明文不落库
    assert len(rec["hash"]) == 64 and "salt" in rec  # pbkdf2 哈希 + 盐


def test_token_resolves_to_correct_user():
    a = AuthService()
    token, _ = a.login("13800000001", "dev123")   # developer @ d1
    user = a.resolve(token)
    assert user.id == "u_dev" and user.role == Role.DEVELOPER and user.dept_id == "d1"


def test_invalid_token_returns_none():
    a = AuthService()
    assert a.resolve("garbage") is None
    assert a.resolve(None) is None


def test_expired_token_rejected():
    a = AuthService(session_ttl=-1)               # 立即过期
    token, _ = a.login("13800000000", "admin123")
    assert a.resolve(token) is None


def test_logout_invalidates_token():
    a = AuthService()
    token, _ = a.login("13800000000", "admin123")
    a.logout(token)
    assert a.resolve(token) is None


# ---------- 角色门 ----------
def test_authorize_role_admin_passes():
    a = AuthService()
    user = a.resolve(a.login("13800000000", "admin123")[0])
    ok, _ = authorize_role(user, [Role.ADMIN])
    assert ok is True


def test_authorize_role_user_denied_admin_endpoint():
    a = AuthService()
    user = a.resolve(a.login("13800000003", "user123")[0])  # 普通 user
    ok, reason = authorize_role(user, [Role.ADMIN])
    assert ok is False and "需要角色" in reason


def test_authorize_role_unauthenticated_denied():
    ok, reason = authorize_role(None, [Role.ADMIN])
    assert ok is False and reason == "未认证"


def test_dept_admin_role_resolved():
    a = AuthService()
    user = a.resolve(a.login("13800000002", "da123")[0])
    assert user.role == Role.DEPARTMENT_ADMIN and user.dept_id == "d1"


# ---------- 微信桩 ----------
def test_wechat_qr_not_configured_without_appid():
    # 确保未配置时优雅返回而非崩溃
    old = os.environ.pop("WECHAT_APPID", None)
    try:
        res = wechat_qr()
        assert res["status"] == "not_configured"
    finally:
        if old:
            os.environ["WECHAT_APPID"] = old


def test_wechat_callback_raises_not_implemented():
    a = AuthService()
    try:
        wechat_callback("code", a)
        assert False, "应抛 NotImplementedError"
    except NotImplementedError:
        pass


def test_auth_endpoints_if_fastapi_available():
    """端点级 RBAC 测试：装了 fastapi 才跑（真机），沙箱自动跳过。"""
    try:
        from fastapi.testclient import TestClient  # type: ignore
        from backend.app import app
    except Exception:
        return
    if app is None:
        return
    client = TestClient(app)
    # 登录拿 token
    r = client.post("/v1/auth/login", json={"phone": "13800000003", "password": "user123"})
    assert r.status_code == 200
    token = r.json()["token"]
    # 带 token 访问 /v1/me
    me = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["role"] == "user"
    # 普通 user 访问 admin 专属端点 → 403
    av = client.get("/v1/audit/verify", headers={"Authorization": f"Bearer {token}"})
    assert av.status_code == 403
    # 未认证访问 /v1/me → 401
    assert client.get("/v1/me").status_code == 401
    # admin 登录后可访问 audit/verify
    at = client.post("/v1/auth/login", json={"phone": "13800000000", "password": "admin123"}).json()["token"]
    assert client.get("/v1/audit/verify", headers={"Authorization": f"Bearer {at}"}).status_code == 200


# ---------- 自助注册（强制 user 角色） ----------
def test_register_self_success_returns_token():
    a = AuthService()
    token, msg = a.register_self("13900000001", "secret6")
    assert token and a.resolve(token).role == Role.USER  # 强制 user


def test_register_self_forces_user_role():
    a = AuthService()
    token, _ = a.register_self("13900000002", "secret6")
    u = a.resolve(token)
    assert u.role == Role.USER  # 即便将来客户端想传 admin，也只会是 user


def test_register_duplicate_phone_rejected():
    a = AuthService()
    a.register_self("13900000003", "secret6")
    token, msg = a.register_self("13900000003", "secret6")
    assert token is None and "已注册" in msg


def test_register_validates_phone_and_password():
    a = AuthService()
    assert a.register_self("abc", "secret6")[0] is None        # 手机号非法
    assert a.register_self("13900000004", "123")[0] is None    # 密码太短


def test_register_then_login_works():
    a = AuthService()
    a.register_self("13900000005", "secret6")
    token, _ = a.login("13900000005", "secret6")
    assert token is not None
