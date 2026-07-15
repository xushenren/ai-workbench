// REST 封装。对接现有后端 6 端点；任一失败 fallback 到内置示例数据并标记 offline。
import type { Agent, KnowledgeBase, AdminStats, KBSearchResponse, AdminUser, DeptRequest, AuditKBMeta, AuditReadResult } from "@/types";
import { SAMPLE_AGENTS, SAMPLE_KBS, SAMPLE_STATS } from "./sampleData";
import { currentToken } from "@/stores/useAuthStore";

// 经 vite 代理转发到 http://localhost:9000；生产可改为绝对地址。
const BASE = "/v1";

/** 标记后端是否连通，供 UI 显示"后端服务未连接"。 */
export const backendState = { online: true };

/** 统一请求头：带上当前会话 token（后端据此识别身份/角色）。 */
function authHeaders(): Record<string, string> {
  const t = currentToken();
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}

async function get<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: authHeaders(),
      signal: AbortSignal.timeout(4000),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    backendState.online = true;
    return (await res.json()) as T;
  } catch {
    backendState.online = false; // 触发 UI 离线提示，但用示例数据兜底
    return fallback;
  }
}

export const api = {
  agents: () => get<Agent[]>("/agents", SAMPLE_AGENTS),
  agent: (id: string) =>
    get<Agent | undefined>(`/agents/${id}`, SAMPLE_AGENTS.find((a) => a.id === id)),
  knowledge: () => get<KnowledgeBase[]>("/knowledge", SAMPLE_KBS),
  computeStatus: () => get<AdminStats["tiers"]>("/compute/status", SAMPLE_STATS.tiers),
  adminStats: () => get<AdminStats>("/admin/stats", SAMPLE_STATS),

  async kbSearch(query: string, top_k = 5): Promise<KBSearchResponse> {
    try {
      const res = await fetch(`${BASE}/kb/search`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ query, top_k }),
        signal: AbortSignal.timeout(6000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      backendState.online = true;
      return (await res.json()) as KBSearchResponse;
    } catch {
      backendState.online = false;
      return { query, accessible_kbs: [], results: [] }; // 离线兜底：空结果
    }
  },

  // ---- 管理类（抛错以便 UI 显示具体失败，如 403/400/404）----
  listUsers: () => authedGet<AdminUser[]>("/admin/users"),
  setUserRole: (id: string, role: string) =>
    authedSend(`/admin/users/${id}/role`, { role }),
  assignDepartment: (id: string, dept_id: string | null) =>
    authedSend(`/admin/users/${id}/department`, { dept_id }),
  listDeptRequests: () => authedGet<DeptRequest[]>("/admin/dept/requests"),
  createUser: (u: { phone: string; password?: string; role: string; dept_id?: string }) =>
    authedSend<{ id: string; phone: string; role: string; dept_id: string | null; init_password?: string }>("/admin/users", u),
  deleteUser: (id: string) => authedSend("/admin/users/" + id + "/delete", {}),
  // 对话文件上传
  uploadChatFile: async (file: File, sessionId: string) => {
    const fd = new FormData(); fd.append("file", file); fd.append("session_id", sessionId);
    const t = currentToken();
    const res = await fetch("/v1/files/upload", {
      method: "POST", headers: t ? { Authorization: `Bearer ${t}` } : {}, body: fd,
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
    return res.json();
  },
  sessionFiles: (sid: string) => authedGet<any[]>(`/files/session/${sid}`),
  deleteChatFile: (id: string) => authedSend(`/files/${id}/delete`, {}),
  // 递归进化 / 思考 MD 版本管理
  mdNames: () => authedGet<string[]>("/admin/md/names"),
  mdVersions: (name: string) => authedGet<any[]>("/admin/md/" + encodeURIComponent(name) + "/versions"),
  mdVersion: (id: string) => authedGet<any>("/admin/md/version/" + id),
  mdSave: (name: string, content: string, note?: string) => authedSend("/admin/md/save", { name, content, note }),
  mdSetLive: (id: string) => authedSend("/admin/md/version/" + id + "/set-live", {}),
  mdRollback: (name: string, id: string) => authedSend("/admin/md/" + encodeURIComponent(name) + "/rollback/" + id, {}),
  evalTasks: () => authedGet<any[]>("/admin/eval/tasks"),
  evalRun: () => authedSend<any>("/admin/eval/run", {}),

  // 语音转文字
  voiceAsr: async (audio: Blob) => {
    const fd = new FormData(); fd.append("file", audio, "audio.webm");
    const t = currentToken();
    const res = await fetch("/v1/voice/asr", {
      method: "POST", headers: t ? { Authorization: `Bearer ${t}` } : {}, body: fd,
    });
    if (!res.ok) throw new Error(`ASR HTTP ${res.status}`);
    return res.json() as Promise<{ text?: string }>;
  },

  handleDeptRequest: (reqId: string, action: "approve" | "reject") =>
    authedSend(`/admin/dept/requests/${reqId}/${action}`, {}),
  requestDepartment: (dept_id: string) => authedSend("/dept/request", { dept_id }),

  // ---- 用户批量导入（管理员）----
  importUsers: async (file: File) => {
    const fd = new FormData(); fd.append("file", file);
    const t = currentToken();
    const res = await fetch("/v1/users/import", {
      method: "POST", headers: t ? { Authorization: `Bearer ${t}` } : {}, body: fd,
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
    return res.json();
  },
  downloadUserTemplate: () => {
    const t = currentToken();
    fetch("/v1/users/import/template", { headers: t ? { Authorization: `Bearer ${t}` } : {} })
      .then((r) => r.blob()).then((b) => {
        const url = URL.createObjectURL(b); const a = document.createElement("a");
        a.href = url; a.download = "org_import_template.csv"; a.click(); URL.revokeObjectURL(url);
      });
  },

  // ---- 组织权限管理（org_core 显形，需管理员）----
  orgTree: () => authedGet<any>("/org/tree"),
  orgUsers: () => authedGet<any[]>("/org/users"),
  orgRoles: () => authedGet<any[]>("/org/roles"),
  orgNodes: () => authedGet<any[]>("/org/nodes"),
  orgPerms: () => authedGet<string[]>("/org/perms"),
  orgCreateNode: (b: { parent_id: string; name: string; type: string }) => authedSend("/org/node", b),
  orgRenameNode: (id: string, name: string) => authedSend(`/org/node/${id}/rename`, { name }),
  orgDefineRole: (b: { at_node_id: string; name: string; perm_keys: string[] }) => authedSend("/org/role", b),
  orgGrant: (b: { user_id: string; role_id: string; org_node_id: string; label?: string }) => authedSend("/org/grant", b),
  orgAdminScope: (b: { user_id: string; org_node_id: string }) => authedSend("/org/admin-scope", b),

  // ---- 多级组织架构 Excel 导入 ----
  orgImport: async (file: File, dryRun: boolean) => {
    const fd = new FormData(); fd.append("file", file); fd.append("dry_run", String(dryRun));
    const t = currentToken();
    const res = await fetch("/v1/org/import", {
      method: "POST", headers: t ? { Authorization: `Bearer ${t}` } : {}, body: fd,
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
    return res.json();
  },
  downloadOrgTemplate: () => {
    const t = currentToken();
    fetch("/v1/org/import/template", { headers: t ? { Authorization: `Bearer ${t}` } : {} })
      .then((r) => r.blob()).then((b) => {
        const url = URL.createObjectURL(b); const a = document.createElement("a");
        a.href = url; a.download = "org_template.xlsx"; a.click(); URL.revokeObjectURL(url);
      });
  },

  // ---- 受控审计（仅 auditor）----
  auditKbList: () => authedGet<AuditKBMeta[]>("/audit/kb/list"),
  auditKbRead: (kb_id: string, reason: string) =>
    authedSend<AuditReadResult>("/audit/kb/read", { kb_id, reason }),

  createKb: (name: string, visibility: string, dept_id?: string | null) =>
    authedSend<{ id: string; name: string; type: string; doc_count: number }>(
      "/kb/create", { name, visibility, dept_id: dept_id ?? null }),

  ingestText: (kbId: string, text: string) =>
    authedSend<{ kb_id: string; doc_count: number }>(`/kb/${kbId}/ingest`, { text }),

  createAgent: (payload: Record<string, unknown>) =>
    authedSend<Record<string, unknown>>("/admin/agents", payload),

  // MD 导入（单个）
  importAgentMd: (content: string) =>
    authedSend<Record<string, unknown>>("/agents/import-md", { content }),

  // zip 批量导入：一个压缩包一群智能体
  importAgentsZip: async (file: File, conflict: "skip" | "rename" | "overwrite" = "skip") => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("conflict", conflict);
    const t = currentToken();
    const res = await fetch("/v1/agents/import-zip", {
      method: "POST",
      headers: t ? { Authorization: `Bearer ${t}` } : {},
      body: fd,
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      throw new Error((d as any).detail || `HTTP ${res.status}`);
    }
    return res.json() as Promise<{
      summary: { created: number; skipped: number; failed: number };
      created: { file: string; name: string; id: string }[];
      skipped: { file: string; name: string; reason: string }[];
      failed: { file: string; reason: string }[];
    }>;
  },

  // 模型管理（全需管理员）
  listAllModels: () => authedGet<any[]>("/models/all"),
  models: () => authedGet<any[]>("/models"), // 启用中的模型(聊天选择器用)
  modelProviders: () => authedGet<any[]>("/models/providers"),
  fetchProviderModels: (api_base: string, api_key: string) =>
    authedSend<any>("/models/fetch", { api_base, api_key }),
  createModel: (m: { name: string; api_base: string; api_key: string; model: string; enabled?: boolean }) =>
    authedSend<any>("/models", { enabled: true, ...m }),
  updateModel: (id: string, patch: Record<string, unknown>) =>
    authedSend<any>(`/models/${id}/update`, patch),
  deleteModel: (id: string) => authedSend<any>(`/models/${id}/delete`, {}),

  // 知识库批量入库 (v0.7.1)
  batchIngest: async (kbId: string, files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    const t = currentToken();
    const res = await fetch(`/v1/kb/${kbId}/batch-ingest`, {
      method: "POST", headers: t ? { Authorization: `Bearer ${t}` } : {}, body: fd,
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
    return res.json() as Promise<{
      summary: { ingested: number; skipped: number; failed: number };
      ingested: { file: string; chars: number }[];
      skipped: { file: string; reason: string }[];
      failed: { file: string; reason: string }[];
    }>;
  },
  listParsers: () => authedGet<any[]>("/kb/parsers"),
  addParser: (m: { ext: string; parser?: string; external_cmd?: string; note?: string }) =>
    authedSend("/kb/parsers", m),
  importParsers: (rows: any[]) => authedSend("/kb/parsers/import", { rows }),
  deleteKb: (kbId: string) => authedSend("/kb/" + kbId + "/delete", {}),
  setKbVisibility: (kbId: string, visibility: string) => authedSend("/kb/" + kbId + "/visibility", { visibility }),
  getIngestConfig: () => authedGet<any>("/kb/ingest-config"),
  setIngestConfig: (c: any) => authedSend("/kb/ingest-config", c),
  suggestField: (name: string, sample = "") => authedSend<any>("/kb/fields/suggest", { name, sample }),
  confirmField: (name: string, type: string) => authedSend<any>("/kb/fields/confirm", { name, type }),

  // 白标品牌 (v0.7.2) — getBranding 公开,无需登录
  getBranding: async () => {
    const r = await fetch("/v1/branding");
    if (!r.ok) throw new Error("branding fetch failed");
    return r.json() as Promise<{
      platform_name: string; logo_url: string; favicon_url: string;
      brand_color: string; brand_color_dark: string; lock_accent: boolean; login_tagline: string;
    }>;
  },
  putBranding: async (b: Record<string, unknown>) => {
    const t = currentToken();
    const r = await fetch("/v1/branding", {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
      body: JSON.stringify(b),
    });
    if (!r.ok) throw new Error((await r.json().catch(()=>({}))).detail || `HTTP ${r.status}`);
    return r.json();
  },

  uploadKbDoc: async (kbId: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const t = currentToken();
    const res = await fetch(`/v1/kb/${kbId}/upload`, {
      method: "POST",
      headers: t ? { Authorization: `Bearer ${t}` } : {},
      body: fd,
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      throw new Error((d as any).detail || `HTTP ${res.status}`);
    }
    return res.json() as Promise<{ kb_id: string; doc_count: number }>;
  },
};

/** 带鉴权的 GET，失败抛错（含状态码），供管理类 UI 显示具体原因。 */
async function authedGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: authHeaders(), signal: AbortSignal.timeout(6000) });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

/** 带鉴权的 POST，失败抛错。 */
async function authedSend<T = unknown>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(6000),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}
