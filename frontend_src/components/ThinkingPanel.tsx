// 右侧思考面板。Claude 式克制：阶段用图标 + 灰阶左边框深浅区分，
// 不用五彩；仅 BLOCK 状态使用警示色。只渲染 public_trace 的 display。
import { useEffect, useRef, useState } from "react";
import {
  Brain, FileSearch, ShieldCheck, Wrench, Cpu, ClipboardList,
  CircleSlash, Loader2, Check, HelpCircle, PanelRightClose,
  ChevronDown, ChevronRight,
} from "lucide-react";
import type { PublicTraceFrame } from "@/types";
import { useChatStore, useUIStore } from "@/stores/useStore";
import { cn } from "@/lib/utils";

const STAGE_META: Record<PublicTraceFrame["stage"], { label: string; Icon: typeof Brain }> = {
  context: { label: "上下文", Icon: FileSearch },
  harness: { label: "安全门控", Icon: ShieldCheck },
  think: { label: "思考", Icon: Brain },
  tool: { label: "工具调用", Icon: Wrench },
  llm: { label: "推理", Icon: Brain },
  compute: { label: "算力", Icon: Cpu },
  audit: { label: "审计", Icon: ClipboardList },
};

function StatusIcon({ status }: { status: PublicTraceFrame["status"] }) {
  if (status === "running") return <Loader2 size={13} className="animate-spin text-muted" />;
  if (status === "blocked") return <CircleSlash size={13} className="text-warning" />;
  if (status === "ask") return <HelpCircle size={13} className="text-accent" />;
  return <Check size={13} className="text-success" />;
}

function FrameRow({ frame, index }: { frame: PublicTraceFrame; index: number }) {
  const meta = STAGE_META[frame.stage] ?? STAGE_META.context;
  const blocked = frame.status === "blocked";
  return (
    <div
      className={cn(
        "animate-slide-in border-l-2 pl-3 py-2",
        blocked ? "border-warning" : "border-border"
      )}
    >
      <div className="flex items-center gap-2 text-xs text-muted">
        <meta.Icon size={13} className={blocked ? "text-warning" : "text-muted"} />
        <span className="font-medium">{meta.label}</span>
        <span className="tabular-nums opacity-60">#{index + 1}</span>
        {frame.tier && (
          <span className="ml-auto rounded-full bg-surface-2 px-1.5 py-0.5 text-[10px] tabular-nums">
            {frame.tier}
          </span>
        )}
        {!frame.tier && frame.latency_ms != null && (
          <span className="ml-auto tabular-nums opacity-60">{frame.latency_ms}ms</span>
        )}
      </div>
      <div className="mt-1 flex items-start gap-1.5">
        <span className="mt-0.5 shrink-0"><StatusIcon status={frame.status} /></span>
        <p className={cn("text-[13px] leading-snug", blocked ? "text-warning" : "text-text")}>
          {frame.display}
        </p>
      </div>
    </div>
  );
}

export function ThinkingPanel() {
  const steps = useChatStore((s) => s.thinkingSteps);
  const streaming = useChatStore((s) => s.isStreaming);
  const toggleThinking = useUIStore((s) => s.toggleThinking);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [steps.length]);

  const blockedCount = steps.filter((s) => s.status === "blocked").length;

  return (
    <aside className="flex h-full w-[340px] shrink-0 flex-col border-l border-border bg-surface-2/40">
      <header className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Brain size={16} className="text-accent" />
        <h2 className="text-sm font-medium">思考过程</h2>
        <button
          onClick={toggleThinking}
          className="ml-auto rounded-md p-1 text-muted hover:bg-surface-2 hover:text-text"
          aria-label="折叠思考面板"
        >
          <PanelRightClose size={16} />
        </button>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-2">
        {steps.length === 0 ? (
          <p className="mt-8 px-2 text-center text-[13px] text-muted">
            {streaming ? "正在思考…" : "发送消息后，这里会实时展示推理链。"}
          </p>
        ) : (
          steps.map((f, i) => <FrameRow key={i} frame={f} index={i} />)
        )}
      </div>

      {steps.length > 0 && !streaming && (
        <footer className="border-t border-border px-4 py-3 text-xs text-muted">
          共 {steps.length} 步 · 红线触发 {blockedCount} 次 · 审计已记录
        </footer>
      )}
    </aside>
  );
}

/** 内嵌版思考过程：渲染在主对话流里（当前轮回复上方），可折叠。 */
export function InlineThinking() {
  const steps = useChatStore((s) => s.thinkingSteps);
  const streaming = useChatStore((s) => s.isStreaming);
  const [open, setOpen] = useState(true);
  if (steps.length === 0) return null;
  const blocked = steps.filter((s) => s.status === "blocked").length;

  return (
    <div className="mb-3 rounded-card border border-border bg-surface-2/40">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs text-muted hover:text-text"
      >
        <Brain size={14} className="text-accent" />
        <span className="font-medium">思考过程</span>
        <span className="opacity-60">· {steps.length} 步{blocked ? ` · 拦截 ${blocked}` : ""}</span>
        {streaming && <span className="text-accent">思考中…</span>}
        <span className="ml-auto">{open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</span>
      </button>
      {open && (
        <div className="border-t border-border px-2 py-1">
          {steps.map((f, i) => <FrameRow key={i} frame={f} index={i} />)}
        </div>
      )}
    </div>
  );
}
