// CapabilityBar.tsx — 每条 AI 回答下方的"能力条",把网关本事显形:
// 省token、难度/专家路由、安全门控、来源数、模型。数据来自 x_shangan_meta。
import { Coins, Compass, ShieldCheck, BookOpen, Cpu, Zap } from "lucide-react";
import type { ShanganMeta } from "@/types";

const DIFF: Record<string, string> = { easy: "简单", medium: "中等", hard: "困难" };

function Chip({ icon, text, title, tone = "muted" }: { icon: React.ReactNode; text: string; title?: string; tone?: "muted" | "accent" | "good" }) {
  const c = tone === "accent" ? "text-accent" : tone === "good" ? "text-success" : "text-muted";
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded-md bg-surface-2 px-1.5 py-0.5 text-[11px] ${c}`}>
      {icon}{text}
    </span>
  );
}

export function CapabilityBar({ meta }: { meta?: ShanganMeta }) {
  if (!meta) return null;

  // 省 token:缓存命中=省整次;否则看字符节省 + 上下文压缩
  let saveText = "", saveTitle = "", saveTone: "muted" | "accent" | "good" = "muted";
  if (meta.cache_hit) { saveText = "命中缓存 · 省整次回答"; saveTone = "good"; saveTitle = "语义缓存命中,本次几乎零生成成本"; }
  else {
    const parts: string[] = [];
    if (meta.tool_chars_saved && meta.tool_chars_saved > 0) parts.push(`省 ${fmtK(meta.tool_chars_saved)} 字`);
    if (meta.ctx_compressed) parts.push("上下文压缩");
    if (parts.length) { saveText = parts.join(" · "); saveTone = "accent"; saveTitle = "工具裁剪/上下文压缩节省的输入量"; }
  }

  const experts = meta.experts?.filter(Boolean) ?? [];
  const routeText = [DIFF[meta.difficulty ?? ""] ?? meta.difficulty, experts.length ? experts.join("、") : meta.route_level]
    .filter(Boolean).join(" · ");

  const sg = meta.secureguard;
  const sgPass = sg && sg.in === "allow" && sg.out === "allow";

  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
      {saveText && <Chip icon={<Coins size={11} />} text={saveText} title={saveTitle} tone={saveTone} />}
      {routeText && <Chip icon={<Compass size={11} />} text={routeText} title="难度分级与专家路由" />}
      {sg && <Chip icon={<ShieldCheck size={11} />} text={sgPass ? "已过安全门控" : `门控:${sg.in}/${sg.out}`} title="入站/出站安全检查" tone={sgPass ? "good" : "muted"} />}
      {!!meta.sources && meta.sources > 0 && <Chip icon={<BookOpen size={11} />} text={`${meta.sources} 条来源`} title="检索到的引用来源数" />}
      {meta.model && <Chip icon={<Cpu size={11} />} text={meta.model} title="本次应答模型" />}
      {!!meta.artifacts && meta.artifacts > 0 && <Chip icon={<Zap size={11} />} text={`${meta.artifacts} 产物`} title="生成的工作区产物" />}
    </div>
  );
}

function fmtK(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}
