// CustomFieldPanel.tsx — 自定义条目:人给条目名 → AI 判类型+建议值 → 人确认即定。
// 放进知识库条目编辑处。AI 只给建议,人确认才算数(与 0 幻觉一致)。
import { useState } from "react";
import { Sparkles, Check, Loader2 } from "lucide-react";
import { Card, Button } from "@/components/ui/primitives";
import { api } from "@/lib/api";

const TYPES = [
  { id: "bool", label: "是/否" }, { id: "number", label: "数量" },
  { id: "text", label: "文本" }, { id: "date", label: "日期" },
];

export function CustomFieldPanel({ onConfirmed }: { onConfirmed?: (name: string, type: string) => void }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [suggestion, setSuggestion] = useState<{ suggested_type: string; suggested_value: string; rationale: string } | null>(null);
  const [type, setType] = useState("text");
  const [done, setDone] = useState<{ name: string; type: string }[]>([]);

  const ask = async () => {
    if (!name.trim()) return;
    setBusy(true); setSuggestion(null);
    try {
      const s = await api.suggestField(name.trim());
      setSuggestion(s); setType(s.suggested_type);
    } catch {} finally { setBusy(false); }
  };

  const confirm = async () => {
    setBusy(true);
    try {
      await api.confirmField(name.trim(), type);
      setDone((d) => [...d, { name: name.trim(), type }]);
      onConfirmed?.(name.trim(), type);
      setName(""); setSuggestion(null); setType("text");
    } catch {} finally { setBusy(false); }
  };

  return (
    <Card className="p-5">
      <div className="mb-3 text-sm font-medium">自定义条目</div>
      <div className="flex gap-2">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder='条目名,如"是否防火""层高"'
          className="flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm" />
        <Button size="sm" variant="ghost" onClick={ask} disabled={busy || !name.trim()}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} AI 判断
        </Button>
      </div>

      {suggestion && (
        <div className="mt-3 rounded-md bg-surface-2 p-3">
          <div className="mb-1 text-xs text-muted">AI 建议类型(可改,你确认才算数):{suggestion.rationale}</div>
          <div className="mb-2 flex gap-1.5">
            {TYPES.map((t) => (
              <button key={t.id} onClick={() => setType(t.id)}
                className={`rounded-md px-2.5 py-1 text-xs ${type === t.id ? "bg-accent text-white" : "bg-surface text-muted"}`}>
                {t.label}
              </button>
            ))}
          </div>
          <Button size="sm" onClick={confirm} disabled={busy}><Check size={14} /> 确认固定</Button>
        </div>
      )}

      {done.length > 0 && (
        <div className="mt-3 text-xs text-muted">
          已确认:{done.map((d) => `${d.name}(${d.type})`).join("、")}
        </div>
      )}
    </Card>
  );
}
