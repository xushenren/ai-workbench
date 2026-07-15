// 左侧栏:三分区「最近会话 / 知识库 / 智能体」。智能体从顶部收纳到这里。
// 智能体选择用 props 回调(onSelectAgent)驱动,接 ChatView 现有的选择逻辑,避免硬编码 store 细节。
import { useEffect, useState, type ReactNode } from "react";
import { Plus, MessageSquare, Library, Bot, PanelLeftClose } from "lucide-react";
import { useChatStore, useUIStore, useAgentStore } from "@/stores/useStore";
import { api } from "@/lib/api";
import type { KnowledgeBase } from "@/types";
import { cn } from "@/lib/utils";

const SAMPLE_SESSIONS = ["风管安装验收咨询", "GB50243 条款解读", "施工方案初稿"];

export function Sidebar() {
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const newSession = useChatStore((s) => s.newSession);
  const selectedAgentId = useChatStore((s) => s.selectedAgentId);
  // 选择智能体:用 store 里现有的 setter(若名称不同,改这一行)
  const selectAgent = useChatStore((s) => (s as any).setSelectedAgentId ?? (s as any).selectAgent);

  const agents = useAgentStore((s) => s.agents);
  const fetchAgents = useAgentStore((s) => (s as any).fetchAgents);
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);

  useEffect(() => {
    void api.knowledge().then(setKbs);
    if (typeof fetchAgents === "function" && agents.length === 0) void fetchAgents();
  }, []);

  return (
    <aside className="flex h-full w-[260px] shrink-0 flex-col border-r border-border bg-surface-2/40">
      <div className="p-3">
        <button
          onClick={newSession}
          className="flex w-full items-center gap-2 rounded-btn bg-accent px-3 py-2 text-sm font-medium text-white shadow-soft transition-colors hover:bg-accent-hover"
        >
          <Plus size={16} /> 新对话
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2">
        {/* 1) 最近会话 */}
        <SectionLabel>最近会话</SectionLabel>
        {SAMPLE_SESSIONS.map((title, i) => (
          <button
            key={i}
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm text-muted hover:bg-surface-2 hover:text-text",
              i === 0 && "bg-surface-2 text-text"
            )}
          >
            <MessageSquare size={14} className="shrink-0" />
            <span className="truncate">{title}</span>
          </button>
        ))}

        {/* 2) 智能体(从顶部收纳到此) */}
        <SectionLabel className="mt-4">智能体</SectionLabel>
        {agents.length === 0 && (
          <p className="px-2 py-1.5 text-xs text-muted/70">还没有智能体,去「智能体」页创建或导入。</p>
        )}
        {agents.map((a) => (
          <button
            key={a.id}
            onClick={() => selectAgent?.(a.id)}
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm text-muted hover:bg-surface-2 hover:text-text",
              a.id === selectedAgentId && "bg-surface-2 text-text"
            )}
          >
            <span className="shrink-0 text-base leading-none">{a.icon || <Bot size={14} />}</span>
            <span className="truncate">{a.name}</span>
            {a.visibility && a.visibility !== "private" && (
              <span className="ml-auto text-[10px] tabular-nums opacity-60">
                {a.visibility === "public" ? "公共" : "部门"}
              </span>
            )}
          </button>
        ))}

        {/* 3) 知识库 */}
        <SectionLabel className="mt-4">知识库</SectionLabel>
        {kbs.map((kb) => (
          <div key={kb.id} className="flex items-center gap-2 rounded-md px-2 py-2 text-sm text-muted">
            <Library size={14} className="shrink-0" />
            <span className="truncate">{kb.name}</span>
            <span className="ml-auto text-[11px] tabular-nums opacity-60">{kb.doc_count}</span>
          </div>
        ))}
      </div>

      <footer className="flex items-center gap-2 border-t border-border px-4 py-3 text-xs text-muted">
        <span className="h-2 w-2 rounded-full bg-success" />
        算力正常 · 本地 GPU
        <button
          onClick={toggleSidebar}
          className="ml-auto rounded-md p-1 hover:bg-surface-2 hover:text-text"
          aria-label="折叠侧栏"
        >
          <PanelLeftClose size={15} />
        </button>
      </footer>
    </aside>
  );
}

function SectionLabel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cn("px-2 py-1.5 text-[11px] font-medium uppercase tracking-wide text-muted/70", className)}>
      {children}
    </p>
  );
}
