// ws.ts — 数据层(替换原 WebSocket 版)。
// 改为调真实的 /v2/chat/completions(非流式 OpenAI 兼容),并把返回映射成
// 原有回调 onTrace/onDelta/onArtifact/onDone,所以 useStore.ts 的 sendMessage 一行都不用改。
// 失败仍触发 onError → 上层走离线演示。
import type { WsEvent, PublicTraceFrame } from "@/types";
import { currentToken } from "@/stores/useAuthStore";

export interface ChatHandlers {
  onTrace: (frame: PublicTraceFrame) => void;
  onDelta: (text: string) => void;
  onArtifact: (a: Extract<WsEvent, { event: "artifact" }>) => void;
  onDone: (tier?: string, latencyMs?: number, meta?: any) => void;
  onError: (message: string) => void;
}

const ENDPOINT = "/v2/chat/completions";

/** 发起一次对话。返回 close() 用于中断(打字模拟 + 网络请求都会被取消)。 */
export function streamChat(
  payload: { message: string; agent_id: string; session_id: string; model?: string },
  h: ChatHandlers
): () => void {
  const ctrl = new AbortController();
  let cancelled = false;
  let typingTimer: number | undefined;

  (async () => {
    let data: any;
    try {
      const token = currentToken();
      const res = await fetch(ENDPOINT, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          "X-Conversation-Id": payload.session_id,
          "X-Agent-Id": payload.agent_id,
        },
        body: JSON.stringify({ messages: [{ role: "user", content: payload.message }], model: payload.model }),
        signal: ctrl.signal,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      data = await res.json();
    } catch (e: any) {
      if (!cancelled) h.onError(e?.message || "请求失败");
      return;
    }
    if (cancelled) return;

    // 1) 思考过程：用 x_shangan_meta 合成几帧
    framesFromMeta(data?.x_shangan_meta).forEach(h.onTrace);

    // 2) 正文：去掉 ⟦artifact:ID⟧ 占位标记,再模拟打字流式
    const raw: string = data?.choices?.[0]?.message?.content ?? "";
    const text = stripArtifactMarkers(raw);

    // 3) artifacts：映射成工作区结构
    const arts: any[] = Array.isArray(data?.x_shangan_artifacts) ? data.x_shangan_artifacts : [];
    const meta = { ...(data?.x_shangan_meta || {}), cache_hit: data?.x_shangan_cache === "hit" };

    typeOut(text, h.onDelta, () => {
      if (cancelled) return;
      arts.forEach((a) => h.onArtifact(toWorkspaceArtifact(a)));
      h.onDone(meta?.difficulty ?? meta?.model, data?.usage?.total_tokens, meta);
    }, (t) => (typingTimer = t), () => cancelled);
  })();

  return () => {
    cancelled = true;
    ctrl.abort();
    if (typingTimer) window.clearTimeout(typingTimer);
  };
}

/* ----------------- 映射工具 ----------------- */

// /v2 artifact {id,type,title,lang,content} → /app {filename,language,content,icon,runnable}
function toWorkspaceArtifact(a: any): Extract<WsEvent, { event: "artifact" }> {
  const lang = (a.lang || a.type || "text").toLowerCase();
  const title = (a.title || a.id || "artifact").toString();
  const filename = /\.\w+$/.test(title) ? title : `${title}${extFor(lang)}`;
  return {
    event: "artifact",
    filename,
    language: lang,
    content: a.content ?? "",
    icon: iconFor(lang),
    runnable: lang === "html",
  };
}

function extFor(lang: string): string {
  const m: Record<string, string> = {
    python: ".py", javascript: ".js", js: ".js", typescript: ".ts", ts: ".ts",
    html: ".html", css: ".css", json: ".json", bash: ".sh", shell: ".sh",
    sql: ".sql", markdown: ".md", yaml: ".yaml", java: ".java", go: ".go",
  };
  return m[lang] ?? ".txt";
}
function iconFor(lang: string): string {
  if (lang === "python") return "🐍";
  if (lang === "html") return "🌐";
  if (["js", "javascript", "ts", "typescript"].includes(lang)) return "📜";
  if (lang === "json" || lang === "yaml") return "🧾";
  if (lang === "sql") return "🗄️";
  if (["table", "csv"].includes(lang)) return "📊";
  return "📄";
}

// 去掉正文里的 ⟦artifact:ID⟧ 占位整行(artifact 已在右侧工作区单独展示)
function stripArtifactMarkers(s: string): string {
  return s.replace(/^\s*⟦artifact:[^⟧]+⟧\s*$/gm, "").replace(/⟦artifact:[^⟧]+⟧/g, "").replace(/\n{3,}/g, "\n\n").trim();
}

// x_shangan_meta → 思考帧
function framesFromMeta(meta: any): PublicTraceFrame[] {
  if (!meta) return [];
  const f: PublicTraceFrame[] = [];
  const route =
    Array.isArray(meta.experts) && meta.experts.length
      ? `领域路由：${meta.experts.join("、")}`
      : `领域路由：${meta.route_level ?? "通用"}`;
  f.push({ stage: "context", type: "route", display: `${route}（难度：${meta.difficulty ?? "—"}）`, status: "done" });
  const sg = meta.secureguard;
  if (sg) {
    const pass = sg.in === "allow" && sg.out === "allow";
    f.push({
      stage: "harness", type: "gate",
      display: pass ? "✓ 安全检查通过（入站/出站）" : `安全处置：入站 ${sg.in} / 出站 ${sg.out}`,
      status: pass ? "done" : "blocked",
    });
  }
  if (meta.sources) f.push({ stage: "tool", type: "tool_call", display: `检索到 ${meta.sources} 条来源`, status: "done" });
  if (meta.ctx_compressed) f.push({ stage: "think", type: "reason", display: "上下文已压缩", status: "done" });
  if (meta.model) f.push({ stage: "llm", type: "route", display: `模型：${meta.model}`, status: "done", tier: meta.route_level });
  f.push({ stage: "audit", type: "audit", display: "审计已记录（哈希链）", status: "done" });
  return f;
}

// 把整段文本分块,模拟打字机流式
function typeOut(
  text: string, onDelta: (t: string) => void, done: () => void,
  setTimer: (t: number) => void, isCancelled: () => boolean
) {
  const tokens = text.match(/[\s\S]{1,3}/g) ?? [];
  let i = 0;
  const tick = () => {
    if (isCancelled()) return;
    if (i < tokens.length) {
      onDelta(tokens[i++]);
      setTimer(window.setTimeout(tick, 12));
    } else {
      done();
    }
  };
  tick();
}
