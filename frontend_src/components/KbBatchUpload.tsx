// KbBatchUpload.tsx — 批量入库:拖入多个文件或一个 zip,自动解析入库,显示报告。
// 放进 KnowledgeBaseView(选中某个库时显示),或独立面板。props.kbId 为目标库。
import { useState, useRef } from "react";
import { UploadCloud, Loader2, CheckCircle2, SkipForward, AlertTriangle } from "lucide-react";
import { Card } from "@/components/ui/primitives";
import { api } from "@/lib/api";

type Report = Awaited<ReturnType<typeof api.batchIngest>>;

export function KbBatchUpload({ kbId, kbName }: { kbId: string; kbName?: string }) {
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [err, setErr] = useState("");
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handle = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setBusy(true); setErr(""); setReport(null);
    try {
      const rep = await api.batchIngest(kbId, Array.from(files));
      setReport(rep);
    } catch (e: any) { setErr(e.message || "入库失败"); }
    finally { setBusy(false); }
  };

  return (
    <Card className="p-5">
      <div className="mb-1 text-sm font-medium">批量入库{kbName ? ` · ${kbName}` : ""}</div>
      <p className="mb-3 text-xs text-muted">拖入多个文档或一个压缩包(zip 自动解压)。支持 PDF/Word/Excel/PPT/txt/md/csv;扫描件/图片需管理员开启 OCR。</p>

      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); handle(e.dataTransfer.files); }}
        onClick={() => inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center gap-2 rounded-card border border-dashed px-4 py-10 text-center transition-colors ${drag ? "border-accent bg-accent/5" : "border-border hover:bg-surface-2"}`}>
        {busy ? <Loader2 className="animate-spin text-accent" /> : <UploadCloud className="text-accent" />}
        <span className="text-sm">{busy ? "解析入库中…" : "点击或拖入文件 / 压缩包"}</span>
        <input ref={inputRef} type="file" multiple className="hidden"
          accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.ppt,.pptx,.txt,.md,.zip,.png,.jpg,.jpeg"
          onChange={(e) => handle(e.target.files)} />
      </div>

      {err && <div className="mt-3 text-xs text-red-500">{err}</div>}

      {report && (
        <div className="mt-4">
          <div className="mb-2 flex gap-4 text-xs">
            <span className="flex items-center gap-1 text-accent"><CheckCircle2 size={14} />入库 {report.summary.ingested}</span>
            <span className="flex items-center gap-1 text-muted"><SkipForward size={14} />跳过 {report.summary.skipped}</span>
            <span className="flex items-center gap-1 text-red-500"><AlertTriangle size={14} />失败 {report.summary.failed}</span>
          </div>
          <div className="max-h-44 overflow-y-auto rounded-md bg-surface-2 p-2 text-xs">
            {report.ingested.map((r, i) => <div key={"i" + i} className="text-accent">✓ {r.file} ({r.chars} 字)</div>)}
            {report.skipped.map((r, i) => <div key={"s" + i} className="text-muted">– {r.file}:{r.reason}</div>)}
            {report.failed.map((r, i) => <div key={"f" + i} className="text-red-500">✗ {r.file}:{r.reason}</div>)}
          </div>
        </div>
      )}
    </Card>
  );
}
