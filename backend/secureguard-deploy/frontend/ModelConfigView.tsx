// 管理员模型配置页：增删改查模型。API key 输入后只回传打码值，留空表示不修改。
import { useEffect, useState } from "react";
import { Plus, Trash2, Save, Cpu, X } from "lucide-react";
import { api } from "@/lib/api";
import type { ModelInfo } from "@/types";

const EMPTY = { name: "", api_base: "", api_key: "", model: "", enabled: true };

export function ModelConfigView() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ ...EMPTY });
  const [err, setErr] = useState("");

  const load = () => { void api.listAllModels().then((m) => setModels(Array.isArray(m) ? m : [])).catch(() => setModels([])); };
  useEffect(load, []);

  const create = async () => {
    setErr("");
    if (!draft.name.trim() || !draft.model.trim()) { setErr("显示名与模型标识必填"); return; }
    try {
      await api.createModel(draft);
      setDraft({ ...EMPTY }); setAdding(false); load();
    } catch (e) { setErr(e instanceof Error ? e.message : "创建失败"); }
  };

  const toggle = async (m: ModelInfo) => { await api.updateModel(m.id, { enabled: !m.enabled }).catch(() => {}); load(); };
  const remove = async (m: ModelInfo) => {
    if (m.id === "builtin") return;
    if (!confirm(`删除模型「${m.name}」？`)) return;
    await api.deleteModel(m.id).catch(() => {}); load();
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <div className="mb-6 flex items-center gap-2">
        <Cpu size={20} className="text-text" />
        <h1 className="text-lg font-semibold">模型配置</h1>
        <button onClick={() => setAdding(true)} className="ml-auto flex items-center gap-1.5 rounded-btn bg-text px-3 py-1.5 text-sm text-bg hover:opacity-90">
          <Plus size={15} /> 新增模型
        </button>
      </div>

      <p className="mb-4 rounded-card border border-border bg-surface-2 px-3 py-2 text-xs text-muted">
        配置后可在聊天框选用。真实 API 调用需后端接入对应模型服务；当前未接入时仍由内置模型应答。API Key 仅保存在后端、不明文回显。
      </p>

      {adding && (
        <div className="mb-4 space-y-2 rounded-card border border-border bg-surface p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">新增模型</span>
            <button onClick={() => { setAdding(false); setErr(""); }} className="text-muted hover:text-text"><X size={16} /></button>
          </div>
          <Field label="显示名" value={draft.name} onChange={(v) => setDraft({ ...draft, name: v })} placeholder="如 DeepSeek-V3" />
          <Field label="模型标识" value={draft.model} onChange={(v) => setDraft({ ...draft, model: v })} placeholder="如 deepseek-chat" />
          <Field label="API 地址" value={draft.api_base} onChange={(v) => setDraft({ ...draft, api_base: v })} placeholder="https://api.deepseek.com/v1" />
          <Field label="API Key" value={draft.api_key} onChange={(v) => setDraft({ ...draft, api_key: v })} placeholder="sk-..." type="password" />
          {err && <p className="text-xs text-warning">{err}</p>}
          <button onClick={create} className="flex items-center gap-1.5 rounded-btn bg-text px-3 py-1.5 text-sm text-bg hover:opacity-90">
            <Save size={14} /> 保存
          </button>
        </div>
      )}

      <div className="space-y-2">
        {models.map((m) => (
          <div key={m.id} className="flex items-center gap-3 rounded-card border border-border bg-surface px-4 py-3">
            <Cpu size={16} className="shrink-0 text-muted" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">{m.name}</span>
                <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-muted">{m.model}</span>
                {m.id === "builtin" && <span className="text-[11px] text-muted">内置</span>}
              </div>
              <div className="truncate text-xs text-muted">{m.api_base || "（内置，无需 API）"}{m.api_key_masked && ` · ${m.api_key_masked}`}</div>
            </div>
            <button onClick={() => toggle(m)} className={`rounded-full px-2 py-0.5 text-xs ${m.enabled ? "bg-surface-2 text-text" : "text-muted"}`} disabled={m.id === "builtin"}>
              {m.enabled ? "已启用" : "已停用"}
            </button>
            {m.id !== "builtin" && (
              <button onClick={() => remove(m)} className="text-muted hover:text-warning" aria-label="删除"><Trash2 size={15} /></button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, type = "text" }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-muted">{label}</span>
      <input
        type={type} value={value} placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-btn border border-border bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-text/40"
      />
    </label>
  );
}
