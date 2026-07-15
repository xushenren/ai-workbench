// /register 注册页：手机号 + 密码 + 确认密码。注册成功即登录并进入 /chat。
// 安全：自助注册的角色由后端强制为 user，前端不提供角色选择（防提权）。
import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Loader2, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/primitives";
import { useAuthStore } from "@/stores/useAuthStore";

export function RegisterPage() {
  const navigate = useNavigate();
  const register = useAuthStore((s) => s.register);
  const loading = useAuthStore((s) => s.loading);
  const serverError = useAuthStore((s) => s.error);

  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [localErr, setLocalErr] = useState("");

  const submit = async () => {
    setLocalErr("");
    if (!/^1[3-9]\d{9}$/.test(phone)) { setLocalErr("请输入有效的 11 位手机号"); return; }
    if (password.length < 6) { setLocalErr("密码至少 6 位"); return; }
    if (password !== confirm) { setLocalErr("两次输入的密码不一致"); return; }
    const ok = await register(phone, password);
    if (ok) navigate("/chat");
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm rounded-card border border-border bg-surface p-7 shadow-lift">
        <div className="mb-6 flex flex-col items-center gap-2">
          <div className="flex h-11 w-11 items-center justify-center rounded-card bg-accent text-white">
            <UserPlus size={20} />
          </div>
          <h1 className="font-display text-xl font-semibold">注册新账号</h1>
          <p className="text-xs text-muted">注册后默认为普通用户角色</p>
        </div>

        <div className="space-y-3">
          <Field label="手机号" value={phone} onChange={setPhone} placeholder="13800000000" />
          <Field label="设置密码" value={password} onChange={setPassword} type="password" placeholder="至少 6 位" />
          <Field label="确认密码" value={confirm} onChange={setConfirm} type="password" placeholder="再次输入" onEnter={submit} />
          {(localErr || serverError) && <p className="text-xs text-warning">{localErr || serverError}</p>}
          <Button className="w-full" onClick={submit} disabled={loading}>
            {loading ? <Loader2 size={15} className="animate-spin" /> : "注册并登录"}
          </Button>
        </div>

        <p className="mt-6 text-center text-xs text-muted">
          已有账号？<Link to="/login" className="text-accent hover:underline">去登录</Link>
        </p>
      </div>
    </div>
  );
}

function Field({
  label, value, onChange, type = "text", placeholder, onEnter,
}: {
  label: string; value: string; onChange: (v: string) => void;
  type?: string; placeholder?: string; onEnter?: () => void;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-muted">{label}</span>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && onEnter?.()}
        className="w-full rounded-input border border-border bg-surface-2 px-3 py-2 text-sm outline-none focus:border-accent/60"
      />
    </label>
  );
}
