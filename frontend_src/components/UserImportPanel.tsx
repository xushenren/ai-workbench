// UserImportPanel.tsx — 管理后台:组织架构/员工 Excel·CSV 批量导入。仅管理员。
// 下载模板 → 填好上传 → 批量建用户(手机号/角色/部门)→ 报告(含初始密码,供分发)。
import { useState } from "react";
import { UploadCloud, Download, Loader2, CheckCircle2, SkipForward, AlertTriangle } from "lucide-react";
import { Card, Button } from "@/components/ui/primitives";
import { api } from "@/lib/api";

type Report = {
  summary: { created: number; skipped: number; failed: number };
  created: { phone: string; role: string; dept_id: string; init_password: string }[];
  skipped: { phone: string; reason: string }[];
  failed: { row: string; reason: string }[];
};

export function UserImportPanel() {
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [err, setErr] = useState("");

  const upload = async (f: File | undefined) => {
    if (!f) return;
    setBusy(true); setErr(""); setReport(null);
    try { setReport(await api.importUsers(f)); } catch (e: any) { setErr(e.message || "导入失败"); }
    finally { setBusy(false); }
  };

  return (
    <Card className="mx-auto max-w-2xl p-6">
      <h2 className="mb-1 font-display text-lg font-semibold">组织架构 / 员工批量导入</h2>
      <p className="mb-4 text-sm text-muted">下载模板填好手机号/角色/部门后上传,批量建号。初始密码可留空(自动生成,导入后在报告里分发)。</p>

      <div className="mb-4 flex items-center gap-3">
        <Button size="sm" variant="ghost" onClick={() => api.downloadUserTemplate()}>
          <Download size={14} /> 下载模板
        </Button>
        <span className="text-xs text-muted">列:phone, role(user/developer/department_admin), dept_id, password(可空)</span>
      </div>

      <label className="flex cursor-pointer flex-col items-center gap-2 rounded-card border border-dashed border-border px-4 py-8 text-center hover:bg-surface-2">
        {busy ? <Loader2 className="animate-spin text-accent" /> : <UploadCloud className="text-accent" />}
        <span className="text-sm">{busy ? "导入中…" : "上传 .xlsx 或 .csv"}</span>
        <input type="file" accept=".xlsx,.xls,.csv" className="hidden" disabled={busy} onChange={(e) => upload(e.target.files?.[0])} />
      </label>

      {err && <div className="mt-3 text-xs text-red-500">{err}</div>}

      {report && (
        <div className="mt-4">
          <div className="mb-2 flex gap-4 text-xs">
            <span className="flex items-center gap-1 text-accent"><CheckCircle2 size={14} />建号 {report.summary.created}</span>
            <span className="flex items-center gap-1 text-muted"><SkipForward size={14} />跳过 {report.summary.skipped}</span>
            <span className="flex items-center gap-1 text-red-500"><AlertTriangle size={14} />失败 {report.summary.failed}</span>
          </div>
          {report.created.length > 0 && (
            <div className="mb-2 max-h-40 overflow-y-auto rounded-md bg-surface-2 p-2 text-xs">
              <div className="mb-1 font-medium text-text">新建账号(初始密码,请通知本人尽快改密):</div>
              {report.created.map((r, i) => (
                <div key={i} className="text-muted">{r.phone} · {r.role}{r.dept_id ? ` · ${r.dept_id}` : ""} · 初始密码 <span className="text-accent">{r.init_password}</span></div>
              ))}
            </div>
          )}
          {(report.skipped.length > 0 || report.failed.length > 0) && (
            <div className="max-h-32 overflow-y-auto rounded-md bg-surface-2 p-2 text-xs">
              {report.skipped.map((r, i) => <div key={"s" + i} className="text-muted">– {r.phone}:{r.reason}</div>)}
              {report.failed.map((r, i) => <div key={"f" + i} className="text-red-500">✗ 第{r.row}行:{r.reason}</div>)}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
