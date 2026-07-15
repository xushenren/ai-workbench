// 工作区侧栏：展示 AI 产出的代码 artifact。
// 「代码」tab：语法高亮 + 复制 + 下载；「预览」tab：HTML/JS 在 iframe 里跑（可视化渲染）。
// Python 的可视化（Pyodide 浏览器内执行）留待下一步；当前 Python 的"真跑文本结果"在思考面板 VERIFY 步显示。
import { useState, type ReactNode } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneLight, oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Copy, Download, Check, Code2, Play, PanelRightClose } from "lucide-react";
import { useChatStore, useUIStore } from "@/stores/useStore";
import type { Artifact } from "@/types";

export function WorkspacePanel() {
  const artifacts = useChatStore((s) => s.artifacts);
  const theme = useUIStore((s) => s.theme);
  const toggle = useUIStore((s) => s.toggleWorkspace);
  const [activeIdx, setActiveIdx] = useState(0);
  const [tab, setTab] = useState<"code" | "preview">("code");

  if (artifacts.length === 0) {
    return (
      <aside className="hidden w-[360px] shrink-0 flex-col border-l border-border bg-surface-2/30 lg:flex">
        <Header onClose={toggle} />
        <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-muted">
          工作区空闲。让代码助手写段代码，这里会出现可运行的文件卡片。
        </div>
      </aside>
    );
  }

  const active = artifacts[Math.min(activeIdx, artifacts.length - 1)];
  const canPreview = active.language === "html";

  return (
    <aside className="hidden w-[360px] shrink-0 flex-col border-l border-border bg-surface-2/30 lg:flex">
      <Header onClose={toggle} />

      {/* 文件标签条 */}
      <div className="flex gap-1 overflow-x-auto border-b border-border px-2 py-1.5">
        {artifacts.map((a, i) => (
          <button
            key={a.filename}
            onClick={() => { setActiveIdx(i); setTab("code"); }}
            className={`flex shrink-0 items-center gap-1 rounded-btn px-2 py-1 text-xs ${
              i === activeIdx ? "bg-surface text-text" : "text-muted hover:text-text"
            }`}
          >
            <span>{a.icon}</span>{a.filename}
          </button>
        ))}
      </div>

      {/* 代码/预览 切换 */}
      <div className="flex items-center gap-1 border-b border-border px-3 py-1.5 text-xs">
        <TabBtn active={tab === "code"} onClick={() => setTab("code")} Icon={Code2}>代码</TabBtn>
        {canPreview && <TabBtn active={tab === "preview"} onClick={() => setTab("preview")} Icon={Play}>预览</TabBtn>}
        <div className="ml-auto flex gap-1">
          <CopyBtn text={active.content} />
          <DownloadBtn artifact={active} />
        </div>
      </div>

      {/* 内容 */}
      <div className="min-h-0 flex-1 overflow-auto">
        {tab === "preview" && canPreview ? (
          <iframe
            title="preview"
            sandbox="allow-scripts"
            srcDoc={active.content}
            className="h-full w-full bg-white"
          />
        ) : (
          <SyntaxHighlighter
            language={active.language}
            style={theme === "dark" ? oneDark : oneLight}
            customStyle={{ margin: 0, background: "transparent", fontSize: 13, padding: "12px 14px" }}
            wrapLongLines
          >
            {active.content}
          </SyntaxHighlighter>
        )}
      </div>
    </aside>
  );
}

function Header({ onClose }: { onClose: () => void }) {
  return (
    <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
      <Code2 size={16} className="text-accent" />
      <span className="text-sm font-medium">工作区</span>
      <button onClick={onClose} className="ml-auto rounded-md p-1 text-muted hover:bg-surface-2 hover:text-text" aria-label="关闭工作区">
        <PanelRightClose size={16} />
      </button>
    </div>
  );
}

function TabBtn({ active, onClick, Icon, children }: {
  active: boolean; onClick: () => void; Icon: typeof Code2; children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1 rounded-btn px-2 py-1 ${active ? "bg-surface text-text" : "text-muted hover:text-text"}`}
    >
      <Icon size={13} /> {children}
    </button>
  );
}

function CopyBtn({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={() => { void navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1200); }}
      className="flex items-center gap-1 rounded-btn px-2 py-1 text-muted hover:bg-surface-2 hover:text-text"
    >
      {done ? <Check size={13} className="text-success" /> : <Copy size={13} />}
    </button>
  );
}

function DownloadBtn({ artifact }: { artifact: Artifact }) {
  const download = () => {
    const blob = new Blob([artifact.content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = artifact.filename; a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <button onClick={download} className="flex items-center gap-1 rounded-btn px-2 py-1 text-muted hover:bg-surface-2 hover:text-text">
      <Download size={13} />
    </button>
  );
}
