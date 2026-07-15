import { create } from "zustand";
import type { Agent, Message, PublicTraceFrame, Artifact, ModelInfo } from "@/types";
import { uid } from "@/lib/utils";
import { api } from "@/lib/api";
import { streamChat } from "@/lib/ws";

/* ============================ Chat ============================ */
interface ChatState {
  messages: Message[];
  activeSessionId: string;
  selectedAgentId: string;
  thinkingSteps: PublicTraceFrame[];
  artifacts: Artifact[];
  isStreaming: boolean;
  quotaRemaining: number;
  lastTier: string | null;
  lastTokens: number;
  models: ModelInfo[];
  selectedModelId: string;
  setModel: (id: string) => void;
  loadModels: () => Promise<void>;

  selectAgent: (id: string) => void;
  addMessage: (role: Message["role"], content: string) => string;
  appendToAssistant: (id: string, chunk: string) => void;
  addThinkingStep: (frame: PublicTraceFrame) => void;
  addArtifact: (a: Artifact) => void;
  clearThinking: () => void;
  sendMessage: (text: string) => void;
  newSession: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [
    { id: uid("m_"), role: "assistant", content: "你好，我是企业 AI 工作台。选择上方的智能体后开始对话——右侧会实时显示我的思考过程。" },
  ],
  activeSessionId: uid("s_"),
  selectedAgentId: "general",
  thinkingSteps: [],
  artifacts: [],
  isStreaming: false,
  quotaRemaining: 18247,
  lastTier: null,
  lastTokens: 0,
  models: [],
  selectedModelId: "builtin",

  selectAgent: (id) => set({ selectedAgentId: id }),
  setModel: (id) => set({ selectedModelId: id }),
  loadModels: async () => {
    try { const m = await api.models(); set({ models: Array.isArray(m) ? m : [] }); }
    catch { /* 留空,选择器会提示无可用模型 */ }
  },

  addMessage: (role, content) => {
    const id = uid("m_");
    set((s) => ({ messages: [...s.messages, { id, role, content, streaming: role === "assistant" }] }));
    return id;
  },

  appendToAssistant: (id, chunk) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, content: m.content + chunk } : m)),
    })),

  addThinkingStep: (frame) =>
    set((s) => {
      // 带 step 的思考帧：同一步原地更新（"进行中"→"完成"填入内容），不追加新行
      if (frame.step) {
        const idx = s.thinkingSteps.findIndex((f) => f.step === frame.step);
        if (idx >= 0) {
          const next = s.thinkingSteps.slice();
          next[idx] = frame;
          return { thinkingSteps: next };
        }
        return { thinkingSteps: [...s.thinkingSteps, frame] };
      }
      // 无 step 的帧（安全/工具/审计）：把之前仍 running 且无 step 的结算为 done，再追加
      return {
        thinkingSteps: [
          ...s.thinkingSteps.map((f) =>
            f.status === "running" && !f.step ? { ...f, status: "done" as const } : f),
          frame,
        ],
      };
    }),
  clearThinking: () => set({ thinkingSteps: [] }),

  addArtifact: (a) =>
    set((s) => ({
      // 同名 artifact 覆盖，否则追加
      artifacts: s.artifacts.some((x) => x.filename === a.filename)
        ? s.artifacts.map((x) => (x.filename === a.filename ? a : x))
        : [...s.artifacts, a],
    })),

  sendMessage: (text) => {
    const { selectedAgentId, activeSessionId, selectedModelId } = get();
    get().addMessage("user", text);
    get().clearThinking();
    set({ artifacts: [] });  // 新一轮清空工作区
    const assistantId = get().addMessage("assistant", "");
    set({ isStreaming: true });

    streamChat(
      { message: text, agent_id: selectedAgentId, session_id: activeSessionId, model: selectedModelId },
      {
        onTrace: (frame) => get().addThinkingStep(frame),
        onDelta: (chunk) => get().appendToAssistant(assistantId, chunk),
        onArtifact: (a) => get().addArtifact({
          filename: a.filename, language: a.language, content: a.content,
          icon: a.icon, runnable: a.runnable,
        }),
        onDone: (tier, tokens, meta) =>
          set((s) => ({
            isStreaming: false,
            lastTier: tier ?? s.lastTier,
            lastTokens: typeof tokens === "number" ? tokens : s.lastTokens,
            thinkingSteps: s.thinkingSteps.map((f) =>
              f.status === "running" ? { ...f, status: "done" as const } : f),
            messages: s.messages.map((m) => (m.id === assistantId ? { ...m, streaming: false, meta, tokens } : m)),
          })),
        onError: () => runOfflineDemo(text, assistantId),
      }
    );
  },

  newSession: () =>
    set({
      messages: [{ id: uid("m_"), role: "assistant", content: "新对话已开始。" }],
      activeSessionId: uid("s_"),
      thinkingSteps: [],
    }),
}));

/** 后端不可用时的离线演示：模拟思考帧 + 流式答案，保证界面可预览（关键约束 4）。 */
function runOfflineDemo(text: string, assistantId: string) {
  const get = useChatStore.getState;
  const set = useChatStore.setState;
  const frames: PublicTraceFrame[] = [
    { stage: "context", type: "context_load", display: "已加载用户身份、智能体配置与知识库", status: "done", latency_ms: 12 },
    { stage: "context", type: "gap", display: "未指定设备型号 → 已采用默认值", status: "done" },
    { stage: "context", type: "route", display: "领域路由：机电安装 / 暖通空调", status: "done" },
    { stage: "harness", type: "gate", display: "✓ 安全检查通过", status: "done" },
    { stage: "tool", type: "tool_call", display: "✓ 工具 search_standards 调用完成，返回 5 条结果", status: "done", tool_name: "search_standards", tier: "tier1", latency_ms: 1200 },
    { stage: "compute", type: "route", display: "算力：tier1 本地 GPU", status: "done", tier: "tier1" },
    { stage: "audit", type: "audit", display: "审计已记录（哈希链）", status: "done" },
  ];
  let i = 0;
  const pushFrame = () => {
    if (i < frames.length) {
      get().addThinkingStep(frames[i++]);
      window.setTimeout(pushFrame, 260);
    } else {
      streamAnswer();
    }
  };
  const answer =
    `（演示模式 · 后端未连接）关于「${text}」：\n\n` +
    "根据现有可信文档，要点如下：\n\n" +
    "- **风管安装验收**应符合相关标准条款 `[doc_1]`\n" +
    "- 漏光与漏风检测需在隐蔽前完成 `[doc_2]`\n\n" +
    "```python\n# 示例：泄漏率校验\ndef leak_ok(rate, limit):\n    return rate <= limit\n```\n\n" +
    "如需精确数值，请核对来源原文。";
  const streamAnswer = () => {
    const tokens = answer.match(/[\s\S]{1,3}/g) ?? [];
    let k = 0;
    const tick = () => {
      if (k < tokens.length) {
        get().appendToAssistant(assistantId, tokens[k++]);
        window.setTimeout(tick, 14);
      } else {
        set((s) => ({
          isStreaming: false,
          lastTier: "tier1",
          thinkingSteps: s.thinkingSteps.map((f) =>
            f.status === "running" ? { ...f, status: "done" as const } : f),
          messages: s.messages.map((m) => (m.id === assistantId ? { ...m, streaming: false } : m)),
        }));
      }
    };
    tick();
  };
  pushFrame();
}

/* ============================ Agents ============================ */
interface AgentState {
  agents: Agent[];
  loading: boolean;
  fetchAgents: () => Promise<void>;
}

export const useAgentStore = create<AgentState>((set) => ({
  agents: [],
  loading: false,
  fetchAgents: async () => {
    set({ loading: true });
    const agents = await api.agents();
    set({ agents, loading: false });
  },
}));

/* ============================ UI ============================ */
type Theme = "light" | "dark";

interface UIState {
  sidebarOpen: boolean;
  thinkingPanelOpen: boolean;
  workspaceOpen: boolean;
  theme: Theme;
  toggleSidebar: () => void;
  toggleThinking: () => void;
  toggleWorkspace: () => void;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
}

function applyTheme(t: Theme) {
  const root = document.documentElement;
  if (t === "dark") root.classList.add("dark");
  else root.classList.remove("dark");
}

export const useUIStore = create<UIState>((set, get) => ({
  sidebarOpen: true,
  thinkingPanelOpen: true,
  workspaceOpen: true,
  theme: "light",
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  toggleThinking: () => set((s) => ({ thinkingPanelOpen: !s.thinkingPanelOpen })),
  toggleWorkspace: () => set((s) => ({ workspaceOpen: !s.workspaceOpen })),
  setTheme: (t) => { applyTheme(t); set({ theme: t }); },
  toggleTheme: () => { const t = get().theme === "light" ? "dark" : "light"; applyTheme(t); set({ theme: t }); },
}));
