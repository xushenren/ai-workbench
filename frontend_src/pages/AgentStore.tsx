// /agents 智能体市场：Tab 过滤 + 卡片网格。
import { useEffect, useState } from "react";
import { Wrench, Sparkles, Library, ArrowRight, Upload } from "lucide-react";
import { AgentImportModal } from "@/components/AgentImportModal";
import { Card, Badge, Button, Tabs } from "@/components/ui/primitives";
import { useAgentStore, useChatStore } from "@/stores/useStore";
import { useNavigate } from "react-router-dom";
import { fmt } from "@/lib/utils";
import type { Agent } from "@/types";

type Filter = "all" | "public" | "department" | "private";
const TABS: { id: Filter; label: string }[] = [
  { id: "all", label: "全部" }, { id: "public", label: "公共" },
  { id: "department", label: "部门" }, { id: "private", label: "我的" },
];

export function AgentStore() {
  const { agents, fetchAgents } = useAgentStore();
  const selectAgent = useChatStore((s) => s.selectAgent);
  const navigate = useNavigate();
  const [filter, setFilter] = useState<Filter>("all");
  const [showImport, setShowImport] = useState(false);

  useEffect(() => { if (agents.length === 0) void fetchAgents(); }, [agents.length, fetchAgents]);

  const shown = agents.filter((a) => filter === "all" || a.visibility === filter);

  const use = (a: Agent) => { selectAgent(a.id); navigate("/chat"); };

  return (
    <div className="mx-auto h-full max-w-5xl overflow-y-auto px-6 py-8">
      <h1 className="font-display text-2xl font-semibold tracking-tight">智能体市场</h1>
      <p className="mt-1 text-sm text-muted">选择一个垂直智能体开始对话。公共智能体只回答其所属领域的问题。</p>

      <div className="mt-5 flex items-center justify-between">
        <Tabs tabs={TABS} value={filter} onChange={setFilter} />
        <Button size="sm" onClick={() => setShowImport(true)}>
          <Upload size={14} className="mr-1" />导入
        </Button>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {shown.map((a) => (
          <Card key={a.id} className="flex flex-col p-5 transition-shadow hover:shadow-lift">
            <div className="flex items-start gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-card bg-accent/10 text-xl">{a.icon}</div>
              <div className="min-w-0">
                <h3 className="font-medium">{a.name}</h3>
                <p className="text-xs text-muted">{domainLabel(a.domain)}</p>
              </div>
            </div>
            <p className="mt-3 line-clamp-3 flex-1 text-sm leading-relaxed text-muted">{a.description}</p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <Badge><Wrench size={11} className="mr-1" /> 工具 {a.tools_count}</Badge>
              <Badge><Sparkles size={11} className="mr-1" /> Skill {a.skills_count}</Badge>
              <Badge><Library size={11} className="mr-1" /> 知识库 {a.kb_count}</Badge>
            </div>
            <div className="mt-4 flex items-center justify-between border-t border-border pt-3">
              <span className="text-xs text-muted">🆓 免费 {fmt(a.free_quota_tokens)}/月</span>
              <Button size="sm" onClick={() => use(a)}>使用 <ArrowRight size={14} /></Button>
            </div>
          </Card>
        ))}
      </div>

      {showImport && <AgentImportModal onClose={() => setShowImport(false)} onImported={fetchAgents} />}

      {shown.length === 0 && (
        <p className="mt-16 text-center text-sm text-muted">该分类下还没有智能体。</p>
      )}
    </div>
  );
}

function domainLabel(d: string): string {
  const map: Record<string, string> = {
    general: "通用", electromechanical: "机电安装", software: "软件开发",
    data_ml: "数据 / ML", hr: "人力资源",
  };
  return map[d] ?? d;
}
