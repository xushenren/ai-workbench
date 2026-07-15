// /audit 知识库审计（仅 auditor）：列出全部库（含他人私有），选库 + 必填理由读取原文。
// 受控的关键在 UI 上也明示：每次读取都会被记录。这是唯一能看他人私有原文的通道。
import { useEffect, useState } from "react";
import { ShieldAlert, FileSearch, Loader2, Lock } from "lucide-react";
import { Card, Badge, Button } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { AuditKBMeta, AuditReadResult } from "@/types";

const TYPE_LABEL: Record<AuditKBMeta["type"], string> = {
  public: "公共", department: "部门", private: "私有",
};

export function AuditView() {
  const [kbs, setKbs] = useState<AuditKBMeta[]>([]);
  const [selected, setSelected] = useState<AuditKBMeta | null>(null);
  const [reason, setReason] = useState("");
  const [result, setResult] = useState<AuditReadResult | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const [reading, setReading] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.auditKbList()
      .then(setKbs)
      .catch((e) => setErr((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  const doRead = async () => {
    if (!selected || !reason.trim()) return;
    setReading(true); setErr(""); setResult(null);
    try {
      const r = await api.auditKbRead(selected.id, reason.trim());
      setResult(r);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setReading(false);
    }
  };

  return (
    <div className="mx-auto h-full max-w-5xl overflow-y-auto px-6 py-8">
      <div className="flex items-center gap-2">
        <ShieldAlert size={20} className="text-warning" />
        <h1 className="font-display text-2xl font-semibold tracking-tight">知识库审计</h1>
        <Badge className="ml-2 border-warning/40 bg-warning/10 text-warning">审计员专用</Badge>
      </div>

      {/* 受控提示：明示会被记录 */}
      <div className="mt-3 flex items-start gap-2 rounded-card border border-warning/30 bg-warning/5 px-3 py-2.5 text-xs text-warning">
        <Lock size={14} className="mt-0.5 shrink-0" />
        <span>
          这是唯一能读取他人私有库原文的通道。<strong className="font-semibold">每一次读取都会写入不可篡改的审计链</strong>
          （记录：谁、何时、读了哪个库、理由），可被更高层复核。请仅在合规审计需要时使用。
        </span>
      </div>

      {err && <p className="mt-3 rounded-card border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">{err}</p>}

      <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-[300px_1fr]">
        {/* 全部库列表 */}
        <Card className="overflow-hidden">
          <div className="border-b border-border bg-surface-2/50 px-4 py-2.5 text-xs font-medium text-muted">
            全部知识库（含他人私有）
          </div>
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted">
              <Loader2 size={15} className="animate-spin" /> 加载中…
            </div>
          ) : (
            kbs.map((kb) => (
              <button
                key={kb.id}
                onClick={() => { setSelected(kb); setResult(null); }}
                className={`flex w-full items-center gap-2 border-b border-border px-4 py-2.5 text-left text-sm last:border-0 hover:bg-surface-2 ${
                  selected?.id === kb.id ? "bg-surface-2" : ""
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{kb.name}</div>
                  <div className="truncate text-xs text-muted">owner: {kb.owner_id ?? "—"} · {kb.doc_count} 篇</div>
                </div>
                <Badge className={kb.type === "private" ? "border-warning/30 text-warning" : ""}>
                  {TYPE_LABEL[kb.type]}
                </Badge>
              </button>
            ))
          )}
        </Card>

        {/* 读取面板 */}
        <Card className="p-5">
          {!selected ? (
            <p className="py-10 text-center text-sm text-muted">从左侧选择一个知识库进行审计读取。</p>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <FileSearch size={16} className="text-accent" />
                <h2 className="font-medium">{selected.name}</h2>
                <Badge className="ml-1">{TYPE_LABEL[selected.type]}</Badge>
                <span className="text-xs text-muted">owner: {selected.owner_id ?? "—"}</span>
              </div>

              <label className="mt-4 block">
                <span className="mb-1 block text-xs text-muted">审计理由（必填，将记入审计链）</span>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={2}
                  placeholder="如：合规抽查 2026Q2 / 用户投诉核查 #1234"
                  className="w-full resize-none rounded-input border border-border bg-surface-2 px-3 py-2 text-sm outline-none focus:border-accent/60"
                />
              </label>
              <Button className="mt-3" onClick={doRead} disabled={!reason.trim() || reading}>
                {reading ? <Loader2 size={15} className="animate-spin" /> : "读取并记录"}
              </Button>

              {result && (
                <div className="mt-5 border-t border-border pt-4">
                  <p className="mb-2 text-xs text-success">✓ 已读取并记入审计链（理由：{result.reason}）</p>
                  <div className="space-y-2">
                    {result.documents.map((d) => (
                      <div key={d.doc_id} className="rounded-card border border-border bg-surface-2/40 p-3">
                        <div className="mb-1 text-[11px] text-muted">{d.doc_id}</div>
                        <p className="text-sm leading-relaxed">{d.content}</p>
                      </div>
                    ))}
                    {result.documents.length === 0 && <p className="text-sm text-muted">该库暂无文档。</p>}
                  </div>
                </div>
              )}
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
