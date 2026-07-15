// AgentImportModal.tsx — 导入智能体:单个 .md 或 zip 批量(一包多个),含冲突策略 + 导入报告。
// 放进 AgentStore:加"导入"按钮打开本弹窗;成功后 onImported 刷新列表。
import { useState } from "react";
import { X, UploadCloud, Loader2, CheckCircle2, SkipForward, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/primitives";
import { api } from "@/lib/api";

type Report = Awaited<ReturnType<typeof api.importAgentsZip>>;
const CONFLICT = [
  { id: "skip", label: "跳过同名" },
  { id: "rename", label: "改名导入" },
  { id: "overwrite", label: "覆盖同名" },
] as const;

export function AgentImportModal({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const [conflict, setConflict] = useState<"skip" | "rename" | "overwrite">("skip");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [report, setReport] = useState<Report | null>(null);

  const onFile = async (f: File | undefined) => {
    if (!f) return;
    setBusy(true); setErr(""); setReport(null);
    try {
      if (f.name.toLowerCase().endsWith(".zip")) {
        const rep = await api.importAgentsZip(f, conflict);
        setReport(rep); onImported();
      } else if (f.name.toLowerCase().endsWith(".md")) {
        const text = await f.text();
        await api.importAgentMd(text); onImported();
        setReport({ summary: { created: 1, skipped: 0, failed: 0 },
          created: [{ file: f.name, name: f.name, id: "" }], skipped: [], failed: [] });
      } else {
        setErr("请选择 .md 或 .zip 文件");
      }
    } catch (e: any) {
      setErr(e.message || "导入失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <div className="w-[min(520px,94vw)] rounded-card border border-border bg-surface p-6 shadow-lift">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold">导入智能体</h2>
          <button onClick={onClose} aria-label="关闭" className="text-muted hover:text-text"><X size={18} /></button>
        </div>

        <div className="mb-3">
          <div className="mb-1 text-xs text-muted">同名冲突时</div>
          <div className="flex gap-1.5">
            {CONFLICT.map((c) => (
              <button key={c.id} onClick={() => setConflict(c.id)}
                className={`rounded-md px-2.5 py-1 text-xs ${conflict === c.id ? "bg-accent text-white" : "bg-surface-2 text-muted"}`}>
                {c.label}
              </button>
            ))}
          </div>
        </div>

        <label className="flex cursor-pointer flex-col items-center gap-2 rounded-card border border-dashed border-border px-4 py-8 text-center hover:bg-surface-2">
          {busy ? <Loader2 className="animate-spin text-accent" /> : <UploadCloud className="text-accent" />}
          <span className="text-sm">{busy ? "导入中…" : "点击选择 .md(单个)或 .zip(一包多个)"}</span>
          <span className="text-xs text-muted">zip ≤20MB · 单包 ≤200 个</span>
          <input type="file" accept=".md,.zip" className="hidden" disabled={busy}
            onChange={(e) => onFile(e.target.files?.[0])} />
        </label>

        {err && <div className="mt-3 text-xs text-red-500">{err}</div>}

        {report && (
          <div className="mt-4 text-sm">
            <div className="mb-2 flex gap-4 text-xs">
              <span className="flex items-center gap-1 text-accent"><CheckCircle2 size={14} />成功 {report.summary.created}</span>
              <span className="flex items-center gap-1 text-muted"><SkipForward size={14} />跳过 {report.summary.skipped}</span>
              <span className="flex items-center gap-1 text-red-500"><AlertTriangle size={14} />失败 {report.summary.failed}</span>
            </div>
            <div className="max-h-40 overflow-y-auto rounded-md bg-surface-2 p-2 text-xs">
              {report.created.map((r, i) => <div key={"c" + i} className="text-accent">✓ {r.name}</div>)}
              {report.skipped.map((r, i) => <div key={"s" + i} className="text-muted">– {r.name}:{r.reason}</div>)}
              {report.failed.map((r, i) => <div key={"f" + i} className="text-red-500">✗ {r.file}:{r.reason}</div>)}
            </div>
          </div>
        )}

        <div className="mt-5 flex justify-end">
          <Button size="sm" onClick={onClose}>完成</Button>
        </div>
      </div>
    </div>
  );
}
