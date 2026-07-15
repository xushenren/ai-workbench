// 单条消息气泡。AI 侧 Markdown 渲染 + 代码高亮；流式时显示闪烁光标；
// 拦截态只显示"已被安全策略拦截"，不回显任何 rule_id。
import ReactMarkdown from "react-markdown";
import type { CSSProperties } from "react";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark, oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import { ShieldAlert, Bot } from "lucide-react";
import type { Message } from "@/types";
import { useUIStore } from "@/stores/useStore";
import { cn } from "@/lib/utils";
import { CapabilityBar } from "@/components/CapabilityBar";

export function ChatMessage({ message }: { message: Message }) {
  const theme = useUIStore((s) => s.theme);
  const isUser = message.role === "user";

  if (message.blocked) {
    return (
      <div className="animate-fade-in flex justify-start">
        <div className="flex items-center gap-2 rounded-card border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">
          <ShieldAlert size={16} />
          已被安全策略拦截
        </div>
      </div>
    );
  }

  return (
    <div className={cn("animate-fade-in flex gap-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent/12 text-accent">
          <Bot size={15} />
        </div>
      )}
      <div
        className={cn(
          "max-w-[78%] rounded-card px-4 py-2.5 text-[15px]",
          isUser
            ? "bg-accent text-white shadow-soft"
            : "border border-border bg-surface text-text shadow-soft"
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
        ) : (
          <div className="prose-chat">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ className, children, ...props }) {
                  const match = /language-(\w+)/.exec(className || "");
                  const isBlock = match || String(children).includes("\n");
                  return isBlock ? (
                    <SyntaxHighlighter
                      style={(theme === "dark" ? oneDark : oneLight) as Record<string, CSSProperties>}
                      language={match?.[1] ?? "text"}
                      PreTag="div"
                      customStyle={{ margin: 0, borderRadius: 10, fontSize: 13 }}
                    >
                      {String(children).replace(/\n$/, "")}
                    </SyntaxHighlighter>
                  ) : (
                    <code className={className} {...props}>{children}</code>
                  );
                },
              }}
            >
              {message.content || (message.streaming ? "" : " ")}
            </ReactMarkdown>
            {message.streaming && (
              <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-caret-blink bg-accent align-middle" />
            )}
          </div>
        )}
        {!isUser && !message.streaming && message.meta && <CapabilityBar meta={message.meta} />}
      </div>
    </div>
  );
}
