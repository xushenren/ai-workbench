/**
 * ThinkingChain.jsx — L2 分步推理的可视化（对应 megatask PART 10）。
 *
 * 消费 StepwiseReasoner.reason() 的输出：
 *   { steps:[{id,label,status,question,answer,falsify,verification,confidence,duration_ms}],
 *     final_answer, overall_confidence }
 *
 * 设计取向：把“推理”当作可被审问的过程而非黑箱。每一步都暴露 (1)它在答什么
 * (2)它可能错在哪(证伪) (3)它有多确信。证伪区刻意与答案同级、不折叠，让“可能错在哪”
 * 和答案一样显眼——这正是引导模型证伪的 UI 表达。
 *
 * 仅用 React + 内联样式，无外部依赖，方便嵌入任意前端。
 */
import { useState } from "react";

const INK = "#11131a";
const MUTED = "#6b7280";
const LINE = "#e5e7eb";
const GROUND = "#0f766e";   // 接地/可信 —— 深青
const DOUBT = "#b45309";    // 证伪/存疑 —— 琥珀

function confColor(c) {
  if (c >= 0.8) return GROUND;
  if (c >= 0.5) return "#ca8a04";
  return DOUBT;
}

function ConfidenceBar({ value }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ width: 96, height: 6, background: LINE, borderRadius: 99 }}>
        <div style={{
          width: `${Math.round(value * 100)}%`, height: "100%",
          background: confColor(value), borderRadius: 99, transition: "width .4s ease",
        }} />
      </div>
      <span style={{ fontSize: 12, color: confColor(value), fontVariantNumeric: "tabular-nums" }}>
        {value.toFixed(2)}
      </span>
    </div>
  );
}

function StepCard({ step, index, open, onToggle }) {
  const done = step.status === "completed";
  return (
    <div style={{ borderLeft: `2px solid ${done ? GROUND : LINE}`, paddingLeft: 16, marginBottom: 4 }}>
      <button onClick={onToggle} style={{
        all: "unset", cursor: "pointer", display: "flex", width: "100%",
        alignItems: "center", gap: 12, padding: "10px 0",
      }}>
        <span style={{
          flexShrink: 0, width: 22, height: 22, borderRadius: 6,
          display: "grid", placeItems: "center", fontSize: 12, fontWeight: 600,
          background: done ? GROUND : "#fff", color: done ? "#fff" : MUTED,
          border: `1px solid ${done ? GROUND : LINE}`,
        }}>{index + 1}</span>
        <span style={{ flex: 1, fontSize: 14, fontWeight: 600, color: INK }}>{step.label}</span>
        <span style={{ fontSize: 11, color: MUTED, fontVariantNumeric: "tabular-nums" }}>
          {step.duration_ms}ms
        </span>
        <ConfidenceBar value={step.confidence} />
        <span style={{ color: MUTED, transform: open ? "rotate(90deg)" : "none", transition: ".2s" }}>›</span>
      </button>

      {open && (
        <div style={{ padding: "4px 0 16px", display: "grid", gap: 12 }}>
          <Field label="子问题">{step.question}</Field>
          <Field label="答案">{step.answer}</Field>
          {step.verification && <Field label="验证方式">{step.verification}</Field>}
          {/* 证伪区：与答案同级、默认展开，刻意让“可能错在哪”醒目 */}
          <div style={{
            background: "#fffbeb", border: `1px solid #fde68a`,
            borderRadius: 8, padding: "10px 12px",
          }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: DOUBT, letterSpacing: ".04em", marginBottom: 4 }}>
              这个答案可能错在哪
            </div>
            <div style={{ fontSize: 13, color: "#78350f", whiteSpace: "pre-wrap", lineHeight: 1.5 }}>
              {step.falsify}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 700, color: MUTED, letterSpacing: ".04em", marginBottom: 2 }}>
        {label}
      </div>
      <div style={{ fontSize: 13, color: INK, whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{children}</div>
    </div>
  );
}

export default function ThinkingChain({ data }) {
  const demo = {
    steps: [
      {
        id: 1, label: "界定输入与约束", status: "completed", duration_ms: 340,
        question: "这份合同里哪些条款触发违约责任？",
        answer: "识别出 3 类触发条款：交付延期、质量不达标、保密泄露 [doc_1]。",
        verification: "回读原文逐条核对", confidence: 0.9,
        falsify: "假设“延期=违约”可能过强——若合同含不可抗力条款则不成立；检验：检索第 12 条。",
      },
      {
        id: 2, label: "推导赔偿计算口径", status: "completed", duration_ms: 520,
        question: "违约金如何计算？",
        answer: "按未完成金额的 0.5%/日，封顶合同总额 20% [doc_2]。",
        verification: "代入极端值（延期 60 天）验证封顶生效", confidence: 0.72,
        falsify: "假设封顶适用所有违约类型可能错——保密泄露或单独计；若错，正确口径应分类型分别封顶。",
      },
    ],
    final_answer: "合同主要风险集中在交付延期条款，建议补充不可抗力与分类封顶约定。",
    overall_confidence: 0.81,
  };
  const chain = data || demo;
  const [open, setOpen] = useState(() => new Set([0]));
  const toggle = (i) => setOpen((s) => {
    const n = new Set(s); n.has(i) ? n.delete(i) : n.add(i); return n;
  });

  return (
    <div style={{
      fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
      maxWidth: 720, margin: "0 auto", padding: 20, color: INK,
    }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 16 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>推理链</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 12, color: MUTED }}>整体置信度</span>
          <ConfidenceBar value={chain.overall_confidence} />
        </div>
      </div>

      {chain.steps.map((s, i) => (
        <StepCard key={s.id} step={s} index={i} open={open.has(i)} onToggle={() => toggle(i)} />
      ))}

      <div style={{
        marginTop: 16, padding: "14px 16px", background: "#f0fdfa",
        border: `1px solid #99f6e4`, borderRadius: 10,
      }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: GROUND, letterSpacing: ".04em", marginBottom: 4 }}>
          综合结论
        </div>
        <div style={{ fontSize: 14, color: INK, lineHeight: 1.5 }}>{chain.final_answer}</div>
      </div>
    </div>
  );
}
