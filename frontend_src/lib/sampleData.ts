// 内置示例数据。当后端 API 不可用时 fallback，保证前端不白屏（关键约束 4/5）。
import type { Agent, KnowledgeBase, AdminStats } from "@/types";

export const SAMPLE_AGENTS: Agent[] = [
  {
    id: "general", name: "通用助手", icon: "🤖", domain: "general",
    description: "日常问答与写作，可联网，适合非敏感的开放任务。",
    visibility: "public", tools_count: 3, skills_count: 1, kb_count: 1,
    free_quota_tokens: 20000,
  },
  {
    id: "electromechanical", name: "机电安装助手", icon: "🏗️", domain: "electromechanical",
    description: "建筑机电安装专业助手，回答锚定 GB50243 等 339 条标准，自带引用合规校验。",
    visibility: "public", tools_count: 3, skills_count: 3, kb_count: 2,
    free_quota_tokens: 10000,
  },
  {
    id: "code", name: "代码助手", icon: "💻", domain: "software",
    description: "代码生成与审查，强调状态变更三件套与可逆性，敏感任务强制本地算力。",
    visibility: "public", tools_count: 4, skills_count: 2, kb_count: 1,
    free_quota_tokens: 15000,
  },
];

export const SAMPLE_KBS: KnowledgeBase[] = [
  { id: "kb_std", name: "标准库附录", type: "public", doc_count: 339 },
  { id: "kb_plan", name: "施工方案库", type: "department", doc_count: 1988 },
  { id: "kb_notes", name: "我的笔记", type: "private", doc_count: 42 },
];

export const SAMPLE_STATS: AdminStats = {
  users: 128, agents: 12, compute_nodes: 3, monthly_tokens: 2_480_000,
  knowledge_bases: 17, redline_hits: 0,
  tiers: [
    { tier: "tier1", label: "本地 GPU", online: true, endpoint: "http://gpu-01:8001", model: "vertical-70b" },
    { tier: "tier2", label: "自有云端", online: true, endpoint: "http://cloud:8001", model: "qwen-72b" },
    { tier: "tier3", label: "外部 API", online: false, endpoint: "litellm://gateway", model: "deepseek / claude" },
  ],
  quotas: [
    { agent: "机电安装助手", used: 8247, limit: 10000, freeze: "超额冻结至下月 1 日" },
    { agent: "通用助手", used: 20000, limit: 20000, freeze: "已用完，等待重置" },
    { agent: "代码助手", used: 6120, limit: 15000, freeze: "正常" },
  ],
  guards: { redlines: 19, self_monitor: 18, domain_guards: 6, audit_retention_days: 30 },
  recent_audit: [
    { hash: "a3f8c9d", time: "10:42:01", decision: "PASS" },
    { hash: "b7e2f10", time: "10:41:55", decision: "PASS" },
    { hash: "c1d9a44", time: "10:41:30", decision: "BLOCK" },
    { hash: "d8b3e07", time: "10:40:12", decision: "PASS" },
    { hash: "e5a1c92", time: "10:39:58", decision: "PASS" },
  ],
};
