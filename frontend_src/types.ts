// 全局类型。对接 CONTRACT.md 的契约结构。

export type Role = "admin" | "department_admin" | "developer" | "user" | "auditor";

export interface AdminUser {
  id: string;
  phone: string;
  role: Role;
  dept_id: string | null;
}

export interface DeptRequest {
  id: string;
  user_id: string;
  dept_id: string;
  status: "pending" | "approved" | "rejected";
}

export interface AuditKBMeta {
  id: string;
  name: string;
  type: "public" | "department" | "private";
  owner_id: string | null;
  dept_id: string | null;
  doc_count: number;
}

export interface AuditReadResult {
  kb_id: string;
  kb_name: string;
  owner_id: string | null;
  reason: string;
  documents: { doc_id: string; content: string }[];
  audited: boolean;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean; // 流式进行中（显示闪烁光标）
  blocked?: boolean; // 被安全策略拦截
  ask?: boolean; // 需要澄清
  meta?: ShanganMeta;
  tokens?: number; // 能力可视化：省token/专家路由/安全门控等
}

/**
 * 思考面板帧（public_trace）。
 * 注意：本类型**刻意不包含 rule_id / 内部参数**——按 CONTRACT.md §4 的双轨设计，
 * 用户可见轨绝不携带这些字段。类型层面的缺省 = 结构上不可能误渲染。
 */
export interface PublicTraceFrame {
  stage: "context" | "harness" | "tool" | "llm" | "compute" | "audit" | "think";
  type: "context_load" | "gap" | "route" | "gate" | "tool_call" | "audit" | "reason";
  display: string; // 已脱敏，直接渲染
  status: "running" | "done" | "blocked" | "ask";
  step?: string;   // 思考步骤稳定标识：同 step 的帧原地更新（running→done），不追加
  tool_name?: string;
  tier?: string;
  latency_ms?: number;
}

export interface Artifact {
  filename: string;
  language: string;
  content: string;
  icon: string;
  runnable: boolean;
}

export type WsEvent =
  | { event: "trace"; frame: PublicTraceFrame }
  | { event: "delta"; text: string }
  | { event: "artifact"; filename: string; language: string; content: string; icon: string; runnable: boolean }
  | { event: "done"; tier?: string; latency_ms?: number };

export interface Agent {
  id: string;
  name: string;
  description: string;
  domain: string;
  icon?: string;
  visibility: "public" | "department" | "private";
  tools_count: number;
  skills_count: number;
  kb_count: number;
  free_quota_tokens: number;
}

export interface KnowledgeBase {
  id: string;
  name: string;
  type: "public" | "department" | "private";
  doc_count: number;
}

export interface KBSearchHit {
  kb_id: string;
  kb_name: string;
  doc_id: string;
  content: string;
  score: number;
}

export interface KBSearchResponse {
  query: string;
  accessible_kbs: string[];
  results: KBSearchHit[];
}

export interface ShanganMeta {
  route_level?: string;
  experts?: string[];
  difficulty?: string;
  model?: string;
  tool_chars_saved?: number;
  ctx_compressed?: boolean;
  cache_hit?: boolean;
  sources?: number;
  secureguard?: { in: string; out: string; degraded?: boolean };
  artifacts?: number;
}

export interface TierStatus {
  tier: "tier1" | "tier2" | "tier3";
  label: string;
  online: boolean;
  endpoint: string;
  model: string;
}

export interface AdminStats {
  users: number;
  agents: number;
  compute_nodes: number;
  monthly_tokens: number;
  knowledge_bases: number;
  redline_hits: number;
  tiers: TierStatus[];
  quotas: { agent: string; used: number; limit: number; freeze: string }[];
  guards: { redlines: number; self_monitor: number; domain_guards: number; audit_retention_days: number };
  recent_audit: { hash: string; time: string; decision: "PASS" | "BLOCK" }[];
}

export interface ModelInfo {
  id: string; name: string; model: string;
  api_base?: string; api_key_masked?: string; enabled: boolean;
}
