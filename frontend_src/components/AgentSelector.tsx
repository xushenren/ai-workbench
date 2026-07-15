// 聊天区顶部的智能体选择器：横向 pill 按钮组。
import { useEffect } from "react";
import { useAgentStore, useChatStore } from "@/stores/useStore";
import { cn } from "@/lib/utils";

export function AgentSelector() {
  const { agents, fetchAgents } = useAgentStore();
  const selected = useChatStore((s) => s.selectedAgentId);
  const selectAgent = useChatStore((s) => s.selectAgent);

  useEffect(() => {
    if (agents.length === 0) void fetchAgents();
  }, [agents.length, fetchAgents]);

  return (
    <div className="flex flex-wrap items-center gap-2">
      {agents.map((a) => (
        <button
          key={a.id}
          onClick={() => selectAgent(a.id)}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors",
            selected === a.id
              ? "border-accent bg-accent/10 text-accent"
              : "border-border bg-surface text-muted hover:text-text"
          )}
        >
          <span>{a.icon}</span>
          {a.name}
        </button>
      ))}
    </div>
  );
}
