import { Button, Card } from "@/components/ui/primitives";
// KbManagePanel.tsx — 建库 + 入库(多格式上传) + 管理现有库(删除/可见性)。
import { useState } from "react";
import { Plus, Upload, FileText, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { KnowledgeBase } from "@/types";

const VIS = [
  { id: "private", label: "私有" },
  { id: "department", label: "部门" },
  { id: "public", label: "公共" },
];

export function KbManagePanel({ kbs, onChanged }: { kbs: KnowledgeBase[]; onChanged: () => void }) {
  const [name, setName] = useState("");
  const [vis, setVis] = useState("private");
  const [selKb, setSelKb] = useState<string>("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);

  const note = (ok: boolean, t: string) => { setMsg({ ok, t }); setTimeout(() => setMsg(null), 2500); };

  const createKb = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await api.createKb(name.trim(), vis);
      setName(""); onChanged(); note(true, "知识库已创建");
    } catch (e: any) { note(false, e.message || "创建失败"); }
    finally { setBusy(false); }
  };

  const ingest = async () => {
    if (!selKb || !text.trim()) return;
    setBusy(true);
    try {
      const r = await api.ingestText(selKb, text.trim());
      setText(""); onChanged(); note(true, `已入库(共 ${r.doc_count} 段)`);
    } catch (e: any) { note(false, e.message || "入库失败"); }
    finally { setBusy(false); }
  };

  const upload = async (f: File | undefined) => {
    if (!selKb || !f) return;
    setBusy(true);
    try {
      const r = await api.batchIngest(selKb, [f]);
      onChanged(); note(true, `已上传(共 ${r.doc_count} 段)`);
    } catch (e: any) { note(false, e.message || "上传失败"); }
    finally { setBusy(false); }
  };

  return (
    <div>
      <Card className="m-3 p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-medium">
          <Plus size={15} className="text-accent" /> 新建知识库
        </div>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="库名称"
          className="mb-2 w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm" />
        <div className="mb-2 flex gap-1.5">
          {VIS.map((v) => (
            <button key={v.id} onClick={() => setVis(v.id)}
              className={`rounded-md px-2 py-1 text-xs ${vis === v.id ? "bg-accent text-white" : "bg-surface-2 text-muted"}`}>
              {v.label}
            </button>
          ))}
        </div>
        <Button size="sm" onClick={createKb} disabled={busy} className="w-full">创建</Button>

        <div className="my-3 border-t border-border" />

        <div className="mb-2 text-sm font-medium">选择库</div>
        <select value={selKb} onChange={(e) => setSelKb(e.target.value)}
          className="mb-2 w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm">
          <option value="">-- 选一个库 --</option>
          {kbs.map((k: any) => (
            <option key={k.id} value={k.id}>{k.name} ({k.type ?? "private"})</option>
          ))}
        </select>

        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3}
          placeholder="粘贴文本…"
          className="mb-2 w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm resize-none" />
        <div className="flex gap-2">
          <Button size="sm" onClick={ingest} disabled={busy || !selKb || !text.trim()}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />} 入库
          </Button>
          <label className={`cursor-pointer rounded-md border border-border px-2.5 py-1.5 text-xs ${!selKb ? "opacity-50" : "hover:bg-surface-2"}`}>
            上传文档
            <input type="file" accept=".txt,.md,.csv,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx" className="hidden" disabled={!selKb}
              onChange={(e) => upload(e.target.files?.[0])} />
          </label>
        </div>

        {msg && (
          <div className={`mt-2 text-xs ${msg.ok ? "text-accent" : "text-red-500"}`}>{msg.t}</div>
        )}
      </Card>

      <Card className="m-3 p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-medium">
          管理现有库
        </div>
        {kbs.map((k: any) => (
          <div key={k.id} className="mb-1.5 flex items-center gap-2 text-sm">
            <span className="flex-1 truncate">{k.name}</span>
            <select value={k.type ?? "private"}
              onChange={async (e) => { try { await api.setKbVisibility(k.id, e.target.value); onChanged(); note(true, "已改可见性"); } catch (err: any) { note(false, err.message); } }}
              className="rounded-md border border-border bg-surface-2 px-1.5 py-1 text-xs">
              <option value="private">私有</option>
              <option value="department">部门</option>
              <option value="public">公共</option>
            </select>
            <button onClick={async () => { if (confirm("删除知识库「" + k.name + "」及其全部内容?不可撤销。")) { try { await api.deleteKb(k.id); onChanged(); note(true, "已删除"); } catch (err: any) { note(false, err.message); } } }}
              className="text-muted hover:text-red-500" title="删除库">🗑</button>
          </div>
        ))}
      </Card>
    </div>
  );
}
