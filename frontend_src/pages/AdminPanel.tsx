// /admin 后台管理：6 统计卡 + 4 面板（模型配置 / Token 配额 / 安全门控 / 最近审计）。
import { useEffect, useState, type ReactNode } from "react";
import { Users, Bot, Server, Coins, Library, ShieldAlert } from "lucide-react";
import { Card } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { AdminStats } from "@/types";
import { SAMPLE_STATS } from "@/lib/sampleData";
import { cn, fmt } from "@/lib/utils";
import { UserImportPanel } from "@/components/UserImportPanel";

export function AdminPanel() {
  const [stats, setStats] = useState<AdminStats>(SAMPLE_STATS);
  useEffect(() => { void api.adminStats().then(setStats); }, []);

  const cards = [
    { label: "用户", value: fmt(stats.users), Icon: Users },
    { label: "智能体", value: fmt(stats.agents), Icon: Bot },
    { label: "算力节点", value: fmt(stats.compute_nodes), Icon: Server },
    { label: "本月 Token", value: fmt(stats.monthly_tokens), Icon: Coins },
    { label: "知识库", value: fmt(stats.knowledge_bases), Icon: Library },
    { label: "红线触发", value: fmt(stats.redline_hits), Icon: ShieldAlert, warn: stats.redline_hits > 0 },
  ];

  return (
    <div className="mx-auto h-full max-w-5xl overflow-y-auto px-6 py-8">
      <h1 className="font-display text-2xl font-semibold tracking-tight">后台管理</h1>

      {/* 6 统计卡 */}
      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {cards.map((c) => (
          <Card key={c.label} className="p-4">
            <c.Icon size={16} className={cn(c.warn ? "text-warning" : "text-accent")} />
            <p className={cn("mt-2 text-xl font-semibold tabular-nums", c.warn && "text-warning")}>{c.value}</p>
            <p className="text-xs text-muted">{c.label}</p>
          </Card>
        ))}
      </div>

      {/* 5 面板（含用户导入） */}
      <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="lg:col-span-2">
          <UserImportPanel />
        </div>
        <Panel title="模型配置">
          {stats.tiers.map((t) => (
            <div key={t.tier} className="flex items-center gap-2 py-2 text-sm">
              <span className={cn("h-2 w-2 rounded-full", t.online ? "bg-success" : "bg-muted/40")} />
              <span className="font-medium uppercase">{t.tier}</span>
              <span className="text-muted">{t.label}</span>
              <span className="ml-auto truncate text-xs text-muted">{t.model}</span>
            </div>
          ))}
        </Panel>

        <Panel title="Token 配额">
          {stats.quotas.map((q) => {
            const pct = Math.min(100, Math.round((q.used / q.limit) * 100));
            return (
              <div key={q.agent} className="py-2">
                <div className="flex items-center justify-between text-sm">
                  <span>{q.agent}</span>
                  <span className="tabular-nums text-muted">{fmt(q.used)} / {fmt(q.limit)}</span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-2">
                  <div className={cn("h-full rounded-full", pct >= 100 ? "bg-warning" : "bg-accent")} style={{ width: `${pct}%` }} />
                </div>
                <p className="mt-0.5 text-[11px] text-muted">{q.freeze}</p>
              </div>
            );
          })}
        </Panel>

        <Panel title="安全门控">
          <Stat label="红线启用" value={`${stats.guards.redlines} 条`} />
          <Stat label="自省触发器" value={`${stats.guards.self_monitor} 条`} />
          <Stat label="领域护栏" value={`${stats.guards.domain_guards} 个`} />
          <Stat label="审计保留" value={`${stats.guards.audit_retention_days} 天`} />
        </Panel>

        <Panel title="最近审计">
          {stats.recent_audit.map((a, i) => (
            <div key={i} className="flex items-center gap-3 py-1.5 text-sm">
              <code className="rounded bg-surface-2 px-1.5 py-0.5 text-xs">{a.hash}</code>
              <span className="text-muted">{a.time}</span>
              <span className={cn("ml-auto rounded-full px-2 py-0.5 text-xs",
                a.decision === "PASS" ? "bg-success/15 text-success" : "bg-warning/15 text-warning")}>
                {a.decision}
              </span>
            </div>
          ))}
        </Panel>
      </div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card className="p-5">
      <h2 className="mb-2 text-sm font-medium">{title}</h2>
      <div className="divide-y divide-border">{children}</div>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2 text-sm">
      <span className="text-muted">{label}</span>
      <span className="font-medium tabular-nums">{value}</span>
    </div>
  );
}
