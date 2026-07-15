// /kb 知识库检索：左侧可达库列表 + 中间搜索与结果。隔离由后端保证（只搜可达库），
// 页面顶部明示"仅在你可访问的 N 个库中检索"，结果带来源库 + 评分 + 命中高亮。
import { useEffect, useState, type KeyboardEvent, type ReactNode } from "react";
import { Search, Library, ShieldCheck, Loader2, FileText } from "lucide-react";
import { Card, Badge } from "@/components/ui/primitives";
import { KbManagePanel } from "@/components/KbManagePanel";
import { api } from "@/lib/api";
import type { KnowledgeBase, KBSearchHit } from "@/types";

const TYPE_LABEL: Record<KnowledgeBase["type"], string> = {
  public: "公共", department: "部门", private: "私有",
};

export function KnowledgeBaseView() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<KBSearchHit[]>([]);
  const [accessible, setAccessible] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  useEffect(() => { void api.knowledge().then(setKbs); }, []);

  const run = async () => {
    const q = query.trim();
    if (!q) return;
    setLoading(true); setSearched(true);
    const res = await api.kbSearch(q, 8);
    setHits(res.results);
    setAccessible(res.accessible_kbs);
    setLoading(false);
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => { if (e.key === "Enter") void run(); };

  return (
    <div className="flex h-full">
      {/* 左侧：可达知识库 */}
      <KbManagePanel kbs={kbs} onChanged={() => api.knowledge().then(setKbs)} />
      <aside className="hidden w-[260px] shrink-0 flex-col border-r border-border bg-surface-2/40 md:flex">
        <header className="flex items-center gap-2 border-b border-border px-4 py-3 text-sm font-medium">
          <Library size={16} className="text-accent" /> 我的知识库
        </header>
        <div className="flex-1 overflow-y-auto p-3">
          {kbs.length === 0 ? (
            <p className="px-1 text-xs text-muted">没有可访问的知识库。</p>
          ) : (
            kbs.map((kb) => (
              <div key={kb.id} className="mb-1 flex items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-surface-2">
                <FileText size={14} className="shrink-0 text-muted" />
                <span className="truncate">{kb.name}</span>
                <Badge className="ml-auto shrink-0">{TYPE_LABEL[kb.type]}</Badge>
              </div>
            ))
          )}
        </div>
        <footer className="border-t border-border px-4 py-3 text-[11px] text-muted">
          共 {kbs.length} 个可访问库 · 他人私有库不可见
        </footer>
      </aside>

      {/* 中间：搜索 + 结果 */}
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="mx-auto w-full max-w-3xl px-6 py-6">
          <h1 className="font-display text-2xl font-semibold tracking-tight">知识库检索</h1>

          {/* 隔离提示 */}
          <div className="mt-3 flex items-center gap-2 rounded-card border border-success/30 bg-success/5 px-3 py-2 text-xs text-success">
            <ShieldCheck size={14} />
            检索已隔离：仅在你有权访问的库中搜索（公共 + 本部门 + 自己私有），绝不触达他人私有库。
          </div>

          {/* 搜索框 */}
          <div className="mt-4 flex items-center gap-2 rounded-card border border-border bg-surface px-3 py-2 shadow-soft focus-within:border-accent/50">
            <Search size={18} className="text-muted" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKey}
              placeholder="输入关键词，如：风管 验收 漏风率"
              className="flex-1 bg-transparent py-1.5 text-[15px] outline-none placeholder:text-muted/60"
            />
            <button
              onClick={run}
              disabled={!query.trim() || loading}
              className="flex h-8 items-center gap-1.5 rounded-btn bg-accent px-3 text-sm text-white hover:bg-accent-hover disabled:opacity-40"
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : "搜索"}
            </button>
          </div>

          {/* 结果 */}
          <div className="mt-5 space-y-3">
            {loading && <p className="text-sm text-muted">检索中…</p>}

            {!loading && searched && (
              <p className="text-xs text-muted">
                在 {accessible.length} 个可达库中找到 {hits.length} 条结果
                {accessible.length > 0 && <>（{accessible.join("、")}）</>}
              </p>
            )}

            {!loading && hits.map((h, i) => (
              <Card key={`${h.kb_id}-${h.doc_id}-${i}`} className="p-4">
                <div className="mb-1.5 flex items-center gap-2">
                  <Badge className="border-accent/30 bg-accent/10 text-accent">{h.kb_name}</Badge>
                  <span className="text-[11px] text-muted">{h.doc_id}</span>
                  <ScoreBar score={h.score} />
                </div>
                <p className="text-sm leading-relaxed text-text">
                  {highlight(h.content, query)}
                </p>
              </Card>
            ))}

            {!loading && searched && hits.length === 0 && (
              <p className="py-10 text-center text-sm text-muted">没有命中。换个关键词试试。</p>
            )}
            {!searched && (
              <p className="py-10 text-center text-sm text-muted">输入关键词开始检索。</p>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.max(4, Math.min(100, Math.round(score * 100)));
  return (
    <span className="ml-auto flex items-center gap-1.5 text-[11px] text-muted">
      相关度
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-2">
        <span className="block h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
      </span>
    </span>
  );
}

/** 把命中词在内容里高亮。纯函数（不含 hook，可在 map 里安全调用）。 */
function highlight(text: string, query: string): ReactNode {
  const terms = splitTerms(query);
  if (terms.length === 0) return text;
  const re = new RegExp(`(${terms.map(escapeRe).join("|")})`, "gi");
  const parts = text.split(re);
  return parts.map((p, i) =>
    terms.some((t) => t.toLowerCase() === p.toLowerCase())
      ? <mark key={i} className="rounded bg-accent/20 px-0.5 text-accent">{p}</mark>
      : <span key={i}>{p}</span>
  );
}

function splitTerms(query: string): string[] {
  const q = query.trim();
  if (!q) return [];
  const latin = q.match(/[a-zA-Z0-9]+/g) ?? [];
  const cjk = q.match(/[\u4e00-\u9fff]/g) ?? [];
  return Array.from(new Set([...latin, ...cjk])).filter((t) => t.length >= 1);
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
