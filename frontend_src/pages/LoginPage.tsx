// /login 登录页：手机号 + 密码（接 authStore），微信扫码占位，注册入口跳 /register。
import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { QrCode, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/primitives";
import { useAuthStore } from "@/stores/useAuthStore";

export function LoginPage() {
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const loading = useAuthStore((s) => s.loading);
  const serverError = useAuthStore((s) => s.error);

  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");

  const submit = async () => {
    const ok = await login(phone, password);
    if (ok) navigate("/chat");
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm rounded-card border border-border bg-surface p-7 shadow-lift">
        <div className="mb-6 flex flex-col items-center gap-2">
          <div className="flex h-11 w-11 items-center justify-center rounded-card bg-accent text-lg font-semibold text-white">元</div>
          <h1 className="font-display text-xl font-semibold">企业 AI 工作台</h1>
          <p className="text-xs text-muted">登录以继续</p>
        </div>

        <div className="space-y-3">
          <Field label="手机号" value={phone} onChange={setPhone} placeholder="13800000000" />
          <Field label="密码" value={password} onChange={setPassword} type="password" placeholder="********" onEnter={submit} />
          {serverError && <p className="text-xs text-warning">{serverError}</p>}
          <Button className="w-full" onClick={submit} disabled={loading}>
            {loading ? <Loader2 size={15} className="animate-spin" /> : "登录"}
          </Button>
          <p className="text-center text-[11px] text-muted">演示账号：13800000000 / admin123</p>
        </div>

        <div className="my-5 flex items-center gap-3 text-xs text-muted">
          <span className="h-px flex-1 bg-border" /> 或 <span className="h-px flex-1 bg-border" />
        </div>

        <div className="flex flex-col items-center gap-2">
          <div className="flex h-28 w-28 items-center justify-center rounded-card border border-dashed border-border bg-surface-2 text-muted">
            <QrCode size={40} strokeWidth={1.25} />
          </div>
          <p className="text-xs text-muted">微信扫码登录（需配置 AppID）</p>
        </div>

        <p className="mt-6 text-center text-xs text-muted">
          还没有账号？<Link to="/register" className="text-accent hover:underline">注册</Link>
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
