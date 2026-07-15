// AdminBrandingPanel.tsx — 管理后台维护白标:平台名、logo(上传转 data-URL)、主色、锁定、登录标语。
// 仅管理员。保存后调 applyBranding 立即生效。
import { useEffect, useState } from "react";
import { Loader2, Upload } from "lucide-react";
import { Card, Button } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { applyBranding, type Brand } from "@/lib/branding";

const EMPTY: Brand = { platform_name: "", logo_url: "", favicon_url: "", brand_color: "#3b4cca", brand_color_dark: "#8ea2ff", lock_accent: false, login_tagline: "" };

export function AdminBrandingPanel() {
  const [b, setB] = useState<Brand>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const note = (ok: boolean, t: string) => { setMsg({ ok, t }); setTimeout(() => setMsg(null), 2500); };

  useEffect(() => { api.getBranding().then((x) => setB({ ...EMPTY, ...x })).catch(() => {}); }, []);

  const pickLogo = (f: File | undefined) => {
    if (!f) return;
    if (f.size > 500 * 1024) { note(false, "logo 请压到 500KB 内"); return; }
    const r = new FileReader();
    r.onload = () => setB((p: Brand) => ({ ...p, logo_url: String(r.result) }));
    r.readAsDataURL(f);
  };

  const save = async () => {
    setBusy(true);
    try {
      const saved = await api.putBranding(b as any);
      applyBranding(saved as Brand);   // 立即全局生效
      note(true, "已保存并应用");
    } catch (e: any) { note(false, e.message || "保存失败"); }
    finally { setBusy(false); }
  };

  return (
    <Card className="mx-auto max-w-2xl p-6">
      <h2 className="mb-1 font-display text-lg font-semibold">品牌设置(白标)</h2>
      <p className="mb-5 text-sm text-muted">维护平台名称、logo 与主色;面向不同甲方各自配置。</p>

      <div className="space-y-4">
        <Row label="平台名称">
          <input value={b.platform_name} onChange={(e) => setB({ ...b, platform_name: e.target.value })} placeholder="如 某某建工 AI 平台" className={inp} />
        </Row>

        <Row label="Logo">
          <div className="flex items-center gap-3">
            {b.logo_url ? <img src={b.logo_url} alt="logo" className="h-10 w-10 rounded-md border border-border" /> : <div className="grid h-10 w-10 place-items-center rounded-md border border-dashed border-border text-xs text-muted">无</div>}
            <label className="flex cursor-pointer items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-surface-2">
              <Upload size={14} /> 上传图片
              <input type="file" accept="image/*" className="hidden" onChange={(e) => pickLogo(e.target.files?.[0])} />
            </label>
            {b.logo_url && <button onClick={() => setB({ ...b, logo_url: "" })} className="text-xs text-muted hover:text-red-500">清除</button>}
          </div>
        </Row>

        <Row label="主色(强调色基线)">
          <div className="flex items-center gap-3">
            <input type="color" value={b.brand_color} onChange={(e) => setB({ ...b, brand_color: e.target.value })} className="h-9 w-14 rounded-md border border-border bg-surface" />
            <input value={b.brand_color} onChange={(e) => setB({ ...b, brand_color: e.target.value })} className={`${inp} w-32`} />
            <label className="flex items-center gap-2 text-sm text-muted">
              <input type="checkbox" checked={b.lock_accent} onChange={(e) => setB({ ...b, lock_accent: e.target.checked })} /> 锁定(员工不可改)
            </label>
          </div>
        </Row>

        <Row label="登录页标语(可选)">
          <input value={b.login_tagline} onChange={(e) => setB({ ...b, login_tagline: e.target.value })} placeholder="如 让每个项目都有 AI 助手" className={inp} />
        </Row>
      </div>

      <div className="mt-6 flex items-center gap-3">
        <Button size="sm" onClick={save} disabled={busy}>{busy ? <Loader2 size={14} className="animate-spin" /> : null} 保存并应用</Button>
        {msg && <span className={`text-xs ${msg.ok ? "text-accent" : "text-red-500"}`}>{msg.t}</span>}
      </div>
    </Card>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><div className="mb-1 text-xs text-muted">{label}</div>{children}</div>;
}
const inp = "w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm";
