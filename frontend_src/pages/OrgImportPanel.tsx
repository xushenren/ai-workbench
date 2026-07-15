// OrgImportPanel.tsx — 多级组织架构 Excel 导入。仅管理员。
// 下载模板(两张表:组织/人员)→ 上传 → 先预演(dry-run)看报告 → 确认正式导入。
import { useState } from "react";
import { Download, UploadCloud, Loader2, CheckCircle2, AlertTriangle, FlaskConical } from "lucide-react";
import { Card, Button } from "@/components/ui/primitives";
import { api } from "@/lib/api";

type Report = {
  summary: { nodes_created: number; nodes_reused: number; users_created: number; grants_created: number; errors: number; dry_run: boolean };
  nodes_created: string[]; nodes_reused: string[];
  users_created: { phone: string; init_password: string }[];
  grants_created: string[]; errors: { item: string; reason: string }[]; dry_run: boolean;
};

export function OrgImportPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [err, setErr] = useState("");

  const run = async (dryRun: boolean) => {
    if (!file) { setErr("请先选择 Excel 文件"); return; }
    setBusy(true); setErr(""); setReport(null);
    try { setReport(await api.orgImport(file, dryRun)); }
    catch (e: any) { setErr(e.message || "导入失败"); }
    finally { setBusy(false); }
  };

  return (
    <Card className="mx-auto max-w-2xl p-6">
      <h2 className="mb-1 font-display text-lg font-semibold">多级组织架构导入</h2>
      <p className="mb-4 text-sm text-muted">一个 Excel,两张表:「组织」(节点名/上级节点/类型)建多级树;「人员」(手机号/姓名/岗位/所属节点/初始密码)建账号并派任职。一人多行=多个任职(子账号)。</p>

      <div className="mb-4 flex items-center gap-3">
        <Button size="sm" variant="ghost" onClick={() => api.downloadOrgTemplate()}><Download size={14} /> 下载模板</Button>
        <span className="text-xs text-muted">岗位需先在「岗位」里建好;节点按名称去重复用</span>
      </div>

      <label className="flex cursor-pointer flex-col items-center gap-2 rounded-card border border-dashed border-border px-4 py-7 text-center hover:bg-surface-2">
        <UploadCloud className="text-accent" />
        <span className="text-sm">{file ? file.name : "选择 .xlsx 文件"}</span>
        <input type="file" accept=".xlsx,.xls" className="hidden" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setReport(null); }} />
      </label>

      <div className="mt-4 flex items-center gap-2">
        <Button size="sm" variant="ghost" onClick={() => run(true)} disabled={busy || !file}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <FlaskConical size={14} />} 预演(不落库)
        </Button>
        <Button size="sm" onClick={() => run(false)} disabled={busy || !file}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />} 正式导入
        </Button>
        {err && <span className="text-xs text-red-500">{err}</span>}
      </div>

      {report && (
        <div className="mt-5">
          <div className={`mb-2 inline-block rounded-md px-2 py-0.5 text-xs ${report.dry_run ? "bg-amber-500/15 text-amber-600" : "bg-accent/15 text-accent"}`}>
            {report.dry_run ? "预演结果(未写入)" : "已正式导入"}
          </div>
          <div className="mb-2 flex flex-wrap gap-3 text-xs">
            <Stat label="新建节点" n={report.summary.nodes_created} />
            <Stat label="复用节点" n={report.summary.nodes_reused} />
            <Stat label="新建用户" n={report.summary.users_created} />
            <Stat label="派任职" n={report.summary.grants_created} />
            <Stat label="错误" n={report.summary.errors} bad />
          </div>

          {report.users_created.length > 0 && (
            <div className="mb-2 max-h-36 overflow-y-auto rounded-md bg-surface-2 p-2 text-xs">
              <div className="mb-1 font-medium">新建账号(初始密码,请通知本人改密):</div>
              {report.users_created.map((u, i) => <div key={i} className="text-muted">{u.phone} · 初始密码 <span className="text-accent">{u.init_password}</span></div>)}
            </div>
          )}
          {report.errors.length > 0 && (
            <div className="max-h-32 overflow-y-auto rounded-md bg-surface-2 p-2 text-xs">
              {report.errors.map((e, i) => <div key={i} className="flex items-start gap-1 text-red-500"><AlertTriangle size={12} className="mt-0.5 shrink-0" />{e.item}:{e.reason}</div>)}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function Stat({ label, n, bad }: { label: string; n: number; bad?: boolean }) {
  return <span className={`rounded-md bg-surface-2 px-2 py-1 ${bad && n > 0 ? "text-red-500" : "text-muted"}`}>{label} <b className="tabular-nums">{n}</b></span>;
}
