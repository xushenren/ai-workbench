// ModelsView.tsx — 模型管理(找回的功能,接已有后端 /v1/models*)。
// 流程:选常用厂商→自动带出 api_base→填 sk→拉取可选模型→选模型→保存。下方列表可启停/删除。
// 仅管理员可见(后端已 require admin)。把它加进路由 + 左栏"模型"入口。
import { useEffect, useState } from "react";
import { Plus, RefreshCw, Trash2, Loader2, Server } from "lucide-react";
import { Card, Button, Badge } from "@/components/ui/primitives";
import { api } from "@/lib/api";

interface ModelRec { id: string; name: string; model: string; api_base?: string; enabled: boolean }
interface Provider { id?: string; name: string; api_base?: string }

export function ModelsView() {
  const [models, setModels] = useState<ModelRec[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [form, setForm] = useState({ name: "", api_base: "", api_key: "", model: "" });
  const [fetched, setFetched] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);

  const note = (ok: boolean, t: string) => { setMsg({ ok, t }); setTimeout(() => setMsg(null), 2500); };
  const refresh = () => api.listAllModels().then(setModels).catch(() => {});

  useEffect(() => {
    refresh();
    api.modelProviders().then(setProviders).catch(() => setProviders([]));
  }, []);

  const pickProvider = (name: string) => {
    const p = providers.find((x) => x.name === name);
    setForm((f) => ({ ...f, name: f.name || name, api_base: p?.api_base || f.api_base }));
    setFetched([]);
  };

  const fetchModels = async () => {
    if (!form.api_base) { note(false, "请先填写或选择 API 地址"); return; }
    setBusy(true);
    try {
      const r = await api.fetchProviderModels(form.api_base, form.api_key);
      const list: string[] = Array.isArray(r) ? r : (r.models || r.data || []);
      const names = list.map((x: any) => (typeof x === "string" ? x : x.id || x.name)).filter(Boolean);
      setFetched(names);
      note(true, `拉取到 ${names.length} 个模型`);
    } catch (e: any) { note(false, e.message || "拉取失败"); }
    finally { setBusy(false); }
  };

  const save = async () => {
    if (!form.name.trim() || !form.model.trim()) { note(false, "名称和模型必填"); return; }
    setBusy(true);
    try {
      await api.createModel(form);
      setForm({ name: "", api_base: "", api_key: "", model: "" }); setFetched([]);
      refresh(); note(true, "模型已添加");
    } catch (e: any) { note(false, e.message || "保存失败"); }
    finally { setBusy(false); }
  };

  const toggle = async (m: ModelRec) => {
    try { await api.updateModel(m.id, { enabled: !m.enabled }); refresh(); } catch {}
  };
  const remove = async (m: ModelRec) => {
    if (!confirm(`删除模型「${m.name}」?`)) return;
    try { await api.deleteModel(m.id); refresh(); } catch (e: any) { note(false, e.message); }
  };

  return (
    <div className="mx-auto max-w-3xl p-6">
      <h1 className="mb-1 font-display text-xl font-semibold">模型管理</h1>
      <p className="mb-5 text-sm text-muted">添加本地模型或厂商 API(选常用厂商自动带出地址,填 sk 即可)。</p>

      <Card className="mb-6 p-5">
        <div className="mb-3 flex items-center gap-2 text-sm font-medium"><Plus size={15} className="text-accent" /> 添加模型</div>

        {providers.length > 0 && (
          <div className="mb-3">
            <div className="mb-1 text-xs text-muted">常用厂商(自动带出地址)</div>
            <div className="flex flex-wrap gap-1.5">
              {providers.map((p) => (
                <button key={p.name} onClick={() => pickProvider(p.name)}
                  className="rounded-md bg-surface-2 px-2.5 py-1 text-xs text-muted hover:text-text">{p.name}</button>
              ))}
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Field label="显示名称"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={inp} placeholder="如 DeepSeek-Pro" /></Field>
          <Field label="API 地址 (api_base)"><input value={form.api_base} onChange={(e) => setForm({ ...form, api_base: e.target.value })} className={inp} placeholder="https://api.deepseek.com/v1 或 本地 http://localhost:8001/v1" /></Field>
          <Field label="API Key (sk)"><input value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} className={inp} placeholder="sk-… 本地模型可留空" type="password" /></Field>
          <Field label="模型标识 (model)">
            <div className="flex gap-1.5">
              <input value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} className={inp} placeholder="如 deepseek-chat" list="fetched-models" />
              <button onClick={fetchModels} disabled={busy} title="拉取该厂商可选模型"
                className="shrink-0 rounded-md border border-border px-2 hover:bg-surface-2">
                {busy ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              </button>
            </div>
            <datalist id="fetched-models">{fetched.map((m) => <option key={m} value={m} />)}</datalist>
          </Field>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <Button size="sm" onClick={save} disabled={busy}>保存模型</Button>
          {msg && <span className={`text-xs ${msg.ok ? "text-accent" : "text-red-500"}`}>{msg.t}</span>}
        </div>
      </Card>

      <div className="mb-2 flex items-center gap-2 text-sm font-medium"><Server size={15} className="text-accent" /> 已配置模型</div>
      <div className="space-y-2">
        {models.length === 0 && <div className="text-sm text-muted">还没有模型,先在上面添加一个。</div>}
        {models.map((m) => (
          <Card key={m.id} className="flex items-center justify-between p-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-medium">
                {m.name} <Badge>{m.model}</Badge>
                {!m.enabled && <span className="text-xs text-muted">(停用)</span>}
              </div>
              {m.api_base && <div className="truncate text-xs text-muted">{m.api_base}</div>}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button onClick={() => toggle(m)} className="text-xs text-muted hover:text-text">{m.enabled ? "停用" : "启用"}</button>
              <button onClick={() => remove(m)} className="text-muted hover:text-red-500"><Trash2 size={15} /></button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><div className="mb-1 text-xs text-muted">{label}</div>{children}</div>;
}
const inp = "w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm";
