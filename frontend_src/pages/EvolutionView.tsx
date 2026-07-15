// pages/EvolutionView.tsx — 递归进化与提示词版本管理(护城河显形 #11)。仅 admin。
// 用后端 MD 版本端点:看/改/存/上线/回滚思考与门禁提示词 + 评测触发进化。
// 字段做防御式读取(后端返回结构可能略有差异,容错渲染)。
import { useEffect, useMemo, useState } from "react";
import { GitBranch, FileText, Save, Rocket, RotateCcw, Play, Loader2, Check, History } from "lucide-react";
import { Card, Button, Badge } from "@/components/ui/primitives";
import { api } from "@/lib/api";

type Ver = {
  id: string; version?: number | string; note?: string;
  created_at?: string | number; is_live?: boolean; live?: boolean; content?: string;
};

export function EvolutionView() {
  const [tab, setTab] = useState<"prompts" | "eval">("prompts");
  return (
    <div className="mx-auto h-full max-w-5xl overflow-y-auto px-6 py-8">
      <div className="flex items-center gap-2">
        <GitBranch size={20} className="text-accent" />
        <h1 className="font-display text-2xl font-semibold tracking-tight">进化与版本管理</h1>
      </div>
      <p className="mt-1 text-sm text-muted">思考/门禁提示词的版本化:查看、编辑、上线、回滚;评测失败聚类可触发递归进化。</p>

      <div className="mt-4 flex gap-1.5">
        {([["prompts", "提示词版本", FileText], ["eval", "评测与进化", Play]] as const).map(([k, label, Icon]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`flex items-center gap-1.5 rounded-btn px-3 py-1.5 text-sm ${tab === k ? "bg-surface-2 text-text" : "text-muted hover:text-text"}`}>
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>

      {tab === "prompts" ? <PromptVersions /> : <EvalRunner />}
    </div>
  );
}

/* ---------------- 提示词版本管理 ---------------- */
function PromptVersions() {
  const [names, setNames] = useState<string[]>([]);
  const [name, setName] = useState<string>("");
  const [vers, setVers] = useState<Ver[]>([]);
  const [sel, setSel] = useState<Ver | null>(null);
  const [content, setContent] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const toast = (ok: boolean, t: string) => { setMsg({ ok, t }); setTimeout(() => setMsg(null), 2600); };

  useEffect(() => { api.mdNames().then((n: any) => { const list = Array.isArray(n) ? n : (n?.names || []); setNames(list); if (list[0]) setName(list[0]); }).catch(() => {}); }, []);
  useEffect(() => { if (name) loadVers(name); }, [name]);

  const loadVers = async (nm: string) => {
    try {
      const vs = await api.mdVersions(nm);
      setVers(vs || []);
      const live = (vs || []).find((v: Ver) => v.is_live || v.live) || (vs || [])[0];
      if (live) void openVer(live);
    } catch { setVers([]); }
  };
  const openVer = async (v: Ver) => {
    setSel(v);
    try { const full = await api.mdVersion(v.id); setContent(full?.content ?? v.content ?? ""); }
    catch { setContent(v.content ?? ""); }
  };

  const saveNew = async () => {
    setBusy(true);
    try { await api.mdSave(name, content, note || "手动编辑"); setNote(""); await loadVers(name); toast(true, "已保存新版本"); }
    catch (e: any) { toast(false, e.message || "保存失败"); } finally { setBusy(false); }
  };
  const setLive = async (v: Ver) => {
    setBusy(true);
    try { await api.mdSetLive(v.id); await loadVers(name); toast(true, "已切换上线版本"); }
    catch (e: any) { toast(false, e.message); } finally { setBusy(false); }
  };
  const rollback = async (v: Ver) => {
    if (!confirm(`回滚到该版本?当前内容会被其覆盖为新上线版。`)) return;
    setBusy(true);
    try { await api.mdRollback(name, v.id); await loadVers(name); toast(true, "已回滚"); }
    catch (e: any) { toast(false, e.message); } finally { setBusy(false); }
  };

  const isLive = (v: Ver) => Boolean(v.is_live || v.live);

  return (
    <div className="mt-4 grid gap-4 md:grid-cols-[220px_1fr]">
      {/* 提示词文件列表 */}
      <Card className="p-3">
        <div className="mb-2 text-xs font-medium text-muted">提示词文件</div>
        {names.length === 0 && <p className="px-1 text-xs text-muted/70">无(检查 /v1/admin/md/names)</p>}
        {names.map((n) => (
          <button key={n} onClick={() => setName(n)}
            className={`flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-sm ${n === name ? "bg-surface-2 text-text" : "text-muted hover:text-text"}`}>
            <FileText size={13} /> <span className="truncate">{n}</span>
          </button>
        ))}
      </Card>

      {/* 版本 + 编辑 */}
      <div className="space-y-3">
        {msg && <div className={`rounded-md px-3 py-1.5 text-xs ${msg.ok ? "bg-accent/10 text-accent" : "bg-warning/10 text-warning"}`}>{msg.t}</div>}

        <Card className="p-3">
          <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted"><History size={13} /> 版本历史</div>
          <div className="max-h-40 space-y-1 overflow-y-auto">
            {vers.map((v) => (
              <div key={v.id} className={`flex items-center gap-2 rounded-md border px-2 py-1.5 text-sm ${sel?.id === v.id ? "border-accent" : "border-border"}`}>
                <button onClick={() => openVer(v)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
                  <span className="tabular-nums text-muted">v{v.version ?? "?"}</span>
                  <span className="truncate">{v.note || "—"}</span>
                  {isLive(v) && <Badge>上线中</Badge>}
                </button>
                {!isLive(v) && (
                  <>
                    <button onClick={() => setLive(v)} title="设为上线" className="text-muted hover:text-accent"><Rocket size={13} /></button>
                    <button onClick={() => rollback(v)} title="回滚到此版本" className="text-muted hover:text-warning"><RotateCcw size={13} /></button>
                  </>
                )}
              </div>
            ))}
            {vers.length === 0 && <p className="text-xs text-muted/70">该文件暂无版本</p>}
          </div>
        </Card>

        <Card className="p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium text-muted">内容{sel ? `(查看 v${sel.version ?? "?"})` : ""}</span>
          </div>
          <textarea value={content} onChange={(e) => setContent(e.target.value)}
            className="h-72 w-full resize-y rounded-md border border-border bg-surface p-2 font-mono text-xs outline-none focus:border-accent/50"
            placeholder="提示词内容…" />
          <div className="mt-2 flex items-center gap-2">
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="版本说明(可选)"
              className="flex-1 rounded-md border border-border bg-surface px-2 py-1.5 text-sm" />
            <Button size="sm" onClick={saveNew} disabled={busy || !name}>
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} 存为新版本
            </Button>
          </div>
          <p className="mt-1.5 text-[11px] text-muted">编辑后"存为新版本"不会立即上线;在版本历史里点 🚀 设为上线。这样可安全试错、随时回滚(递归进化的护栏)。</p>
        </Card>
      </div>
    </div>
  );
}

/* ---------------- 评测与进化 ---------------- */
function EvalRunner() {
  const [tasks, setTasks] = useState<any[]>([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState("");

  useEffect(() => { api.evalTasks().then((t) => setTasks(t || [])).catch(() => {}); }, []);

  const run = async (taskId?: string) => {
    setRunning(true); setErr(""); setResult(null);
    try { setResult(await api.evalRun(taskId)); }
    catch (e: any) { setErr(e.message || "评测失败"); } finally { setRunning(false); }
  };

  const clusters = result?.failure_clusters || result?.clusters || [];
  const triggered = result?.evolution_triggered ?? result?.triggered;

  return (
    <div className="mt-4 space-y-3">
      <Card className="p-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium">评测任务({tasks.length})</span>
          <Button size="sm" onClick={() => run()} disabled={running}>
            {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />} 跑全部评测
          </Button>
        </div>
        <div className="divide-y divide-border">
          {tasks.map((t, i) => (
            <div key={t.id ?? i} className="flex items-center gap-2 py-2 text-sm">
              <span className="flex-1 truncate">{t.name || t.id || `任务${i + 1}`}</span>
              {t.pass_rate != null && <span className="tabular-nums text-muted">通过率 {Math.round((t.pass_rate) * 100)}%</span>}
              <button onClick={() => run(t.id)} className="text-muted hover:text-accent" title="单独跑"><Play size={13} /></button>
            </div>
          ))}
          {tasks.length === 0 && <p className="py-2 text-xs text-muted/70">暂无评测任务(检查 /v1/admin/eval/tasks)</p>}
        </div>
      </Card>

      {err && <div className="rounded-md bg-warning/10 px-3 py-2 text-xs text-warning">{err}</div>}

      {result && (
        <Card className="p-4">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-sm font-medium">评测结果</span>
            {triggered != null && (
              <Badge>{triggered ? "已触发进化" : "未触发进化"}</Badge>
            )}
          </div>
          {clusters.length > 0 ? (
            <div className="space-y-1.5">
              <p className="text-xs text-muted">失败聚类:</p>
              {clusters.map((c: any, i: number) => (
                <div key={i} className="rounded-md bg-surface-2 px-2 py-1.5 text-xs">
                  <span className="font-medium">{c.label || c.name || `聚类${i + 1}`}</span>
                  {c.count != null && <span className="ml-2 text-muted">×{c.count}</span>}
                  {c.suggestion && <div className="mt-0.5 text-muted">建议:{c.suggestion}</div>}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted">{triggered ? "已触发进化流程" : "本次无失败聚类或结构未知,原始结果:"}</p>
          )}
          {clusters.length === 0 && <pre className="mt-2 max-h-48 overflow-auto rounded bg-surface-2 p-2 text-[11px]">{JSON.stringify(result, null, 2)}</pre>}
        </Card>
      )}
    </div>
  );
}
