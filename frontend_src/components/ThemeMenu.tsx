import { useState } from "react";
import { Sun, Moon, Monitor, Palette } from "lucide-react";
import { applyTheme, getMode } from "@/lib/theme";
import { ACCENT_PRESETS } from "@/lib/accentTheme";
import { bootAccent } from "@/lib/accentTheme";

export function ThemeMenu() {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState(getMode());

  const setM = (m: "light" | "dark" | "system") => { applyTheme(m); setMode(m); };
  const setA = (hex: string) => {
    const rgb = hexToTriple(hex);
    if (rgb) {
      document.documentElement.style.setProperty("--accent", rgb);
      localStorage.setItem("app.accent", hex);
      localStorage.setItem("app.accent.onboarded", "true");
    }
  };

  return (
    <div className="relative">
      <button onClick={() => setOpen((v) => !v)} className="rounded-btn p-2 text-muted hover:bg-surface-2 hover:text-text" title="外观设置">
        <Palette size={16} />
      </button>
      {open && (
        <div className="absolute right-0 top-9 z-30 w-56 rounded-card border border-border bg-surface p-3 shadow-lift">
          <div className="mb-1 text-xs text-muted">主题</div>
          <div className="mb-3 flex gap-1.5">
            {([["light", "浅色", Sun], ["dark", "深色", Moon], ["system", "跟随", Monitor]] as const).map(([k, label, Icon]) => (
              <button key={k} onClick={() => setM(k)}
                className={`flex flex-1 flex-col items-center gap-1 rounded-md py-1.5 text-[11px] ${mode === k ? "bg-surface-2 text-text" : "text-muted hover:text-text"}`}>
                <Icon size={14} /> {label}
              </button>
            ))}
          </div>
          <div className="mb-1 text-xs text-muted">强调色</div>
          <div className="flex flex-wrap gap-2">
            {ACCENT_PRESETS.map((c) => (
              <button key={c} onClick={() => setA(c)} title={c}
                className={`h-6 w-6 rounded-full border-2 ${(localStorage.getItem("app.accent") || "#3B82D8").toLowerCase() === c.toLowerCase() ? "border-text" : "border-transparent"}`}
                style={{ background: c }} />
            ))}
            <input type="color" value={localStorage.getItem("app.accent") || "#3B82D8"}
              onChange={(e) => setA(e.target.value)}
              className="h-6 w-6 cursor-pointer rounded-full border border-border bg-transparent" title="自定义" />
          </div>
        </div>
      )}
    </div>
  );
}

function hexToTriple(hex: string): string | null {
  const h = hex.replace("#", "");
  const n = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const int = parseInt(n || "3b82d8", 16);
  if (isNaN(int)) return null;
  return `${(int >> 16) & 255} ${(int >> 8) & 255} ${int & 255}`;
}
