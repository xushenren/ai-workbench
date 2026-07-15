import { Button } from "@/components/ui/primitives";
// AgentCreateModal.tsx — 新建智能体(名称/可见性/领域/描述 + 多选知识库)。
// 放进 AgentStore:加一个"新建智能体"按钮打开本弹窗;成功后 onCreated 刷新列表。
import { useEffect, useState } from "react";
import { X, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { KnowledgeBase } from "@/types";

const VIS = [
  { id: "private", label: "私有(直接可用)" },
  { id: "department", label: "部门(需审批)" },
  { id: "public", label: "公共(需审批)" },
];
const DOMAINS = [
  { id: "general", label: "通用" }, { id: "electromechanical", label: "机电安装" },
  { id: "software", label: "软件开发" }, { id: "data_ml", label: "数据/ML" },
];

export function AgentCreateModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [visibility, setVis] = useState("private");
  const [domain, setDomain] = useState("general");
  const [description, setDesc] = useState("");
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { void api.knowledge().then(setKbs); }, []);

  const toggle = (id: string) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  const submit = async () => {
    if (!name.trim()) { setErr("请填写名称"); return; }
    setBusy(true); setErr("");
    try {
      await api.createAgent({
        name: name.trim(), visibility, domain, description: description.trim(),
        kb_ids: picked, kb_count: picked.length,
      });
      onCreated(); onClose();
    } catch (e: any) { setErr(e.message || "创建失败"); setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <div className="w-[min(520px,94vw)] rounded-card border border-border bg-surface p-6 shadow-lift">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold">新建智能体</h2>
          <button onClick={onClose} aria-label="关闭" className="text-muted hover:text-text"><X size={18} /></button>
        </div>

        <label className="mb-1 block text-xs text-muted">名称</label>
        <input value={name} onChange={(e) => setName(e.target.value)}
          className="mb-3 w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm" />

        <label className="mb-1 block text-xs text-muted">描述</label>
        <textarea value={description} onChange={(e) => setDesc(e.target.value)} rows={2}
          className="mb-3 w-full resize-y rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm" />

        <div className="mb-3 flex gap-4">
          <div className="flex-1">
            <label className="mb-1 block text-xs text-muted">可见性</label>
            <select value={visibility} onChange={(e) => setVis(e.target.value)}
              className="w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm">
              {VIS.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
            </select>
          </div>
          <div className="flex-1">
            <label className="mb-1 block text-xs text-muted">领域</label>
            <select value={domain} onChange={(e) => setDomain(e.target.value)}
              className="w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm">
              {DOMAINS.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
            </select>
          </div>
        </div>

        <label className="mb-1 block text-xs text-muted">挂载知识库(可多选)</label>
        <div className="mb-3 flex max-h-32 flex-wrap gap-1.5 overflow-y-auto rounded-md border border-border p-2">
          {kbs.length === 0 && <span className="text-xs text-muted">暂无可挂载的知识库,先去知识库页创建。</span>}
          {kbs.map((k) => (
            <button key={k.id} onClick={() => toggle(k.id)}
              className={`rounded-md px-2 py-1 text-xs ${picked.includes(k.id) ? "bg-accent text-white" : "bg-surface-2 text-muted"}`}>
              {k.name}
            </button>
          ))}
        </div>

        {err && <div className="mb-2 text-xs text-red-500">{err}</div>}
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={onClose}>取消</Button>
          <Button size="sm" onClick={submit} disabled={busy}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : null} 创建
          </Button>
        </div>
      </div>
    </div>
  );
}
