// ArtifactPanel.jsx — 上安 /app 的 Artifacts 渲染面板
// 数据来源：聊天响应里的扩展字段 resp.x_shangan_artifacts（Kun 端忽略该字段，互不影响）
// 依赖：仅 React。主题走 CSS 变量，沿用你 /app 现有 design token，未定义时用兜底值。
// 无 localStorage / 无外部库；可直接放进 Vite + React 工程。

import { useEffect, useMemo, useState } from "react";

const TYPE_LABEL = {
  code: "代码",
  markdown: "文档",
  table: "表格",
  mermaid: "流程图",
  calc: "计算书",
};

const wrap = {
  display: "grid",
  gridTemplateColumns: "200px 1fr",
  gap: "12px",
  border: "1px solid var(--sa-border, #e3e3e6)",
  borderRadius: "10px",
  background: "var(--sa-surface, #fff)",
  color: "var(--sa-text, #1a1a1f)",
  fontFamily: "var(--sa-font, system-ui, -apple-system, 'Segoe UI', sans-serif)",
  overflow: "hidden",
  minHeight: "260px",
};

const mono = "var(--sa-mono, 'SF Mono', 'Cascadia Code', 'JetBrains Mono', Menlo, monospace)";

export default function ArtifactPanel({ artifacts = [] }) {
  const [activeId, setActiveId] = useState(artifacts[0]?.id);
  // 新一轮响应换了 artifacts 时，若当前选中项已不存在则回到第一个
  useEffect(() => {
    if (!artifacts.some((a) => a.id === activeId)) {
      setActiveId(artifacts[0]?.id);
    }
  }, [artifacts, activeId]);
  const active = useMemo(
    () => artifacts.find((a) => a.id === activeId) || artifacts[0],
    [artifacts, activeId]
  );

  if (!artifacts.length) {
    return (
      <div style={{ ...wrap, gridTemplateColumns: "1fr", placeItems: "center", color: "var(--sa-muted,#8a8a93)" }}>
        本次回答没有可保存的成果。提出"出方案 / 写计算书 / 生成清单"会在这里产出 Artifact。
      </div>
    );
  }

  return (
    <div style={wrap}>
      <nav style={{ borderRight: "1px solid var(--sa-border,#e3e3e6)", padding: "8px", overflowY: "auto" }}>
        {artifacts.map((a) => {
          const on = a.id === active?.id;
          return (
            <button
              key={a.id}
              onClick={() => setActiveId(a.id)}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "8px 10px",
                marginBottom: "4px",
                borderRadius: "7px",
                border: "none",
                cursor: "pointer",
                background: on ? "var(--sa-accent-soft, #eef2ff)" : "transparent",
                color: on ? "var(--sa-accent, #3b4cca)" : "inherit",
                fontWeight: on ? 600 : 400,
              }}
            >
              <span style={{ fontSize: "11px", opacity: 0.7 }}>{TYPE_LABEL[a.type] || a.type}</span>
              <div style={{ fontSize: "13px", lineHeight: 1.3, overflow: "hidden", textOverflow: "ellipsis" }}>
                {a.title || "未命名"}
              </div>
            </button>
          );
        })}
      </nav>

      <section style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
        <header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "10px 12px",
            borderBottom: "1px solid var(--sa-border,#e3e3e6)",
          }}
        >
          <strong style={{ fontSize: "14px" }}>{active?.title}</strong>
          <Toolbar artifact={active} />
        </header>
        <div style={{ padding: "12px", overflow: "auto", flex: 1 }}>
          <ArtifactBody artifact={active} />
        </div>
      </section>
    </div>
  );
}

function Toolbar({ artifact }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(artifact.content);
      } else {
        // 非 HTTPS / 旧浏览器兜底
        const ta = document.createElement("textarea");
        ta.value = artifact.content;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* 复制失败静默，不打断用户 */
    }
  };
  const download = () => {
    const ext = { code: artifact.lang || "txt", markdown: "md", table: "csv", mermaid: "mmd", calc: "txt" }[artifact.type] || "txt";
    const blob = new Blob([artifact.content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(artifact.title || "artifact").replace(/\s+/g, "_")}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  };
  const btn = {
    border: "1px solid var(--sa-border,#e3e3e6)",
    background: "var(--sa-surface,#fff)",
    borderRadius: "6px",
    padding: "4px 10px",
    fontSize: "12px",
    cursor: "pointer",
    marginLeft: "6px",
  };
  return (
    <div>
      <button style={btn} onClick={copy}>{copied ? "已复制" : "复制"}</button>
      <button style={btn} onClick={download}>下载</button>
    </div>
  );
}

function ArtifactBody({ artifact }) {
  if (!artifact) return null;
  const { type, content, lang } = artifact;

  if (type === "code" || type === "calc") {
    return (
      <pre style={{ margin: 0, fontFamily: mono, fontSize: "12.5px", lineHeight: 1.55, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
        {lang && type === "code" ? <LangBadge lang={lang} /> : null}
        <code>{content}</code>
      </pre>
    );
  }

  if (type === "table") return <CsvTable content={content} />;

  if (type === "mermaid") {
    // 不引第三方库：先展示源码。若 /app 已集成 mermaid，可在此 useEffect 调 mermaid.render。
    return (
      <div>
        <p style={{ margin: "0 0 8px", fontSize: "12px", color: "var(--sa-muted,#8a8a93)" }}>
          流程图源码（/app 接入 mermaid 后自动渲染）
        </p>
        <pre style={{ margin: 0, fontFamily: mono, fontSize: "12.5px", whiteSpace: "pre-wrap" }}>{content}</pre>
      </div>
    );
  }

  // markdown：极简渲染（标题/列表/行内代码），避免引入 md 库；正式版可换 react-markdown
  return <MiniMarkdown content={content} />;
}

function LangBadge({ lang }) {
  return (
    <span style={{ display: "inline-block", fontSize: "10px", color: "var(--sa-muted,#8a8a93)", marginBottom: "6px" }}>
      {lang}
    </span>
  );
}

function CsvTable({ content }) {
  const rows = content.trim().split("\n").map((r) => r.split(/\t|,/));
  if (!rows.length) return null;
  const [head, ...rest] = rows;
  return (
    <table style={{ borderCollapse: "collapse", fontSize: "13px", width: "100%" }}>
      <thead>
        <tr>
          {head.map((c, i) => (
            <th key={i} style={{ border: "1px solid var(--sa-border,#e3e3e6)", padding: "6px 10px", background: "var(--sa-accent-soft,#f5f6fa)", textAlign: "left" }}>
              {c}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rest.map((r, i) => (
          <tr key={i}>
            {r.map((c, j) => (
              <td key={j} style={{ border: "1px solid var(--sa-border,#e3e3e6)", padding: "6px 10px" }}>{c}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MiniMarkdown({ content }) {
  const blocks = content.split("\n").map((line, i) => {
    if (/^#{1,3}\s/.test(line)) {
      const level = line.match(/^#+/)[0].length;
      const text = line.replace(/^#+\s/, "");
      const size = { 1: "18px", 2: "16px", 3: "14px" }[level];
      return <div key={i} style={{ fontWeight: 700, fontSize: size, margin: "10px 0 4px" }}>{text}</div>;
    }
    if (/^[-*]\s/.test(line)) {
      return <div key={i} style={{ paddingLeft: "16px", lineHeight: 1.6 }}>• {line.replace(/^[-*]\s/, "")}</div>;
    }
    if (!line.trim()) return <div key={i} style={{ height: "6px" }} />;
    return <div key={i} style={{ lineHeight: 1.65, fontSize: "13.5px" }}>{line}</div>;
  });
  return <div>{blocks}</div>;
}
