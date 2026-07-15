// 模型选择下拉：聊天框顶部选用已配置的模型。仅列已启用的。
import { useEffect, useState } from "react";
import { ChevronDown, Cpu, Check } from "lucide-react";
import { useChatStore } from "@/stores/useStore";

export function ModelPicker() {
  const models = useChatStore((s) => s.models);
  const selectedModelId = useChatStore((s) => s.selectedModelId);
  const setModel = useChatStore((s) => s.setModel);
  const loadModels = useChatStore((s) => s.loadModels);
  const [open, setOpen] = useState(false);

  useEffect(() => { loadModels(); }, [loadModels]);

  const current = models.find((m) => m.id === selectedModelId) ?? models.find((m) => m.id === "builtin");
  const label = current?.name ?? "内置模型";

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-btn border border-border px-2.5 py-1.5 text-sm text-muted hover:text-text"
        title="选择模型"
      >
        <Cpu size={14} /> <span className="max-w-[140px] truncate">{label}</span>
        <ChevronDown size={13} />
      </button>
      {open && (
        <div className="absolute top-10 left-0 z-20 max-h-72 w-64 overflow-y-auto rounded-card border border-border bg-surface p-1.5 shadow-lift">
          <p className="px-2 py-1 text-[11px] text-muted">选择对话模型</p>
          {models.length === 0 ? (
            <p className="px-2 py-2 text-xs text-muted">暂无可用模型，请管理员在「管理」中配置</p>
          ) : (
            models.map((m) => (
              <button
                key={m.id}
                onClick={() => { setModel(m.id); setOpen(false); }}
                className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-surface-2 ${
                  m.id === selectedModelId ? "text-text" : "text-muted"
                }`}
              >
                <Cpu size={13} className="shrink-0" />
                <span className="flex-1 truncate">{m.name}</span>
                {m.id === selectedModelId && <Check size={13} />}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
