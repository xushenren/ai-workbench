// /chat 主聊天页：左侧栏 + 中间聊天区（思考过程内嵌在对话流里）+ 右侧工作区。
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { SendHorizontal, PanelLeft, Code2 } from "lucide-react";
import { ModelPicker } from "@/components/ModelPicker";
import { api } from "@/lib/api";
import { Paperclip, Mic, Square, X as XIcon } from "lucide-react";
import { Sidebar } from "@/components/Sidebar";
// import ArtifactPanel from "@/components/ArtifactPanel"; // JSX file, unused - ws.ts now handles artifacts via WorkspacePanel
import { InlineThinking } from "@/components/ThinkingPanel";
import { WorkspacePanel } from "@/components/WorkspacePanel";
import { ChatMessage } from "@/components/ChatMessage";
import { AgentSelector } from "@/components/AgentSelector";
import { useAgentStore, useChatStore, useUIStore } from "@/stores/useStore";
import { fmt } from "@/lib/utils";

export function ChatView() {
  const messages = useChatStore((s) => s.messages);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const artifacts = useChatStore((s) => s.artifacts);
  const quota = useChatStore((s) => s.quotaRemaining);
  const lastTokens = useChatStore((s) => s.lastTokens);
  const selectedAgentId = useChatStore((s) => s.selectedAgentId);
  const agents = useAgentStore((s) => s.agents);

  const sidebarOpen = useUIStore((s) => s.sidebarOpen);
  const workspaceOpen = useUIStore((s) => s.workspaceOpen);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const toggleWorkspace = useUIStore((s) => s.toggleWorkspace);

  const [draft, setDraft] = useState("");
  const [files, setFiles] = useState<{ id: string; filename: string }[]>([]);
  const [recording, setRecording] = useState(false);
  const recRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickBottom = useRef(true);  // 用户是否贴着底部；手动上滚后为 false，不再强拉

  // 监听滚动：距底 <80px 视为"贴底"
  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    stickBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  };

  useEffect(() => {
    // 只有贴底时才自动跟随；用户上翻看历史时不打断
    if (stickBottom.current) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [messages]);

  const agentName = agents.find((a) => a.id === selectedAgentId)?.name ?? "通用助手";
  // 最后一条助手消息：思考过程内嵌到它上方
  const lastAssistantId = [...messages].reverse().find((m) => m.role === "assistant")?.id;

  const submit = () => {
    const text = draft.trim();
    if (!text || isStreaming) return;
    sendMessage(text);
    setDraft("");
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  };

  const onPickFile = async (f?: File) => {
    if (!f) return;
    try {
      const res = await api.uploadChatFile(f, activeSessionId);
      setFiles((xs) => [...xs, { id: res.id ?? res.file_id ?? res.filename, filename: res.filename ?? f.name }]);
    } catch (e) { alert((e as Error).message); }
  };
  const removeFile = async (id: string) => {
    try { await api.deleteChatFile(id); } catch {}
    setFiles((xs) => xs.filter((x) => x.id !== id));
  };

  const toggleRecord = async () => {
    if (recording) { recRef.current?.stop(); setRecording(false); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => chunksRef.current.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        try {
          const { text } = await api.voiceAsr(blob);
          if (text) setDraft((d: string) => (d ? d + " " : "") + text);
        } catch (e) { alert("语音识别失败:" + (e as Error).message); }
      };
      mr.start(); recRef.current = mr; setRecording(true);
    } catch { alert("无法访问麦克风"); }
  };

  // pull activeSessionId from store
  const activeSessionId = useChatStore((s) => s.activeSessionId);

  return (
    <div className="flex h-full">
      {sidebarOpen && <div className="hidden md:flex"><Sidebar /></div>}

      <section className="flex min-w-0 flex-1 flex-col">
        {/* 顶部：折叠按钮 + 智能体选择器 + 工作区开关 */}
        <div className="flex items-center gap-3 border-b border-border px-4 py-2.5">
          {!sidebarOpen && (
            <button onClick={toggleSidebar} className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text" aria-label="展开侧栏">
              <PanelLeft size={16} />
            </button>
          )}
          <span className="text-sm font-medium text-text">{agentName}</span>
          {!workspaceOpen && artifacts.length > 0 && (
            <button onClick={toggleWorkspace} className="ml-auto flex items-center gap-1.5 rounded-btn px-2.5 py-1.5 text-sm text-muted hover:bg-surface-2 hover:text-text">
              <Code2 size={15} /> 工作区 · {artifacts.length}
            </button>
          )}
        </div>

        {/* 消息区：思考过程内嵌在最后一条助手消息上方 */}
        <div ref={scrollRef} onScroll={onScroll} style={{ overflowAnchor: "none" }} className="flex-1 overflow-y-auto">
          <div className="mx-auto flex max-w-3xl flex-col gap-5 px-4 py-6">
            
          {messages.map((m) => (
              <div key={m.id}>
                {m.id === lastAssistantId && m.role === "assistant" && <InlineThinking />}
                <ChatMessage message={m} />
              </div>
            ))}
          </div>
        </div>

        {/* 输入区 */}
        <div className="border-t border-border px-4 py-3">
          <div className="mx-auto max-w-3xl">
              <div className="mb-1.5 flex items-center gap-2">
                <ModelPicker />
                <label className="flex cursor-pointer items-center gap-1 rounded-btn border border-border px-2 py-1.5 text-sm text-muted hover:text-text" title="上传文档">
                  <Paperclip size={14} />
                  <input type="file" className="hidden" onChange={(e) => onPickFile(e.target.files?.[0])} />
                </label>
                <button onClick={toggleRecord}
                  className={`flex items-center gap-1 rounded-btn border px-2 py-1.5 text-sm ${recording ? "border-red-400 text-red-500" : "border-border text-muted hover:text-text"}`}
                  title={recording ? "停止录音" : "语音输入"}>
                  {recording ? <Square size={14} /> : <Mic size={14} />}
                  {recording ? "停止" : ""}
                </button>
              </div>
              {files.length > 0 && (
                <div className="mb-1.5 flex flex-wrap gap-1.5">
                  {files.map((f) => (
                    <span key={f.id} className="flex items-center gap-1 rounded bg-surface-2 px-2 py-0.5 text-xs text-muted">
                      {f.filename}
                      <button onClick={() => removeFile(f.id)} className="hover:text-red-500"><XIcon size={11} /></button>
                    </span>
                  ))}
                </div>
              )}
            <div className="flex items-end gap-2 rounded-card border border-border bg-surface p-2 shadow-soft focus-within:border-accent/50">
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={onKey}
                rows={1}
                placeholder={`向「${agentName}」提问…  (Enter 发送，Shift+Enter 换行)`}
                className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-[15px] outline-none placeholder:text-muted/60"
              />
              <button
                onClick={submit}
                disabled={!draft.trim() || isStreaming}
                className="flex h-9 w-9 items-center justify-center rounded-btn bg-accent text-white transition-colors hover:bg-accent-hover disabled:opacity-40"
                aria-label="发送"
              >
                <SendHorizontal size={16} />
              </button>
            </div>
            <div className="mt-1.5 flex items-center justify-between px-1 text-xs text-muted">
              <span>{agentName}</span>
              <span className="tabular-nums">{lastTokens > 0 && <span className="mr-3">本次 {fmt(lastTokens)} tokens</span>}本月剩余 {fmt(quota)} tokens</span>
            </div>
          </div>
        </div>
      </section>

      {workspaceOpen && <WorkspacePanel />}
    </div>
  );
}
