// FirstRunColorPicker.tsx — 首次登录的个性化选色(吸收 Kun 进门体验)。
// 用 /app 自己的 Tailwind 令牌(bg-surface/text/border/accent)绘制,选色实时全站预览。
import { useEffect, useState } from "react";
import { ACCENT_PRESETS, applyAccent, saveAccent, getSavedAccent } from "@/lib/accentTheme";

export function FirstRunColorPicker({ onDone }: { onDone: () => void }) {
  const [accent, setAccent] = useState(getSavedAccent());

  // 选色即全站实时预览(仅改变量,确认时才持久化)
  useEffect(() => { applyAccent(accent); }, [accent]);

  const finish = (hex: string) => { saveAccent(hex); onDone(); };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 animate-fade-in" role="dialog" aria-modal="true" aria-label="选择你的强调色">
      <div className="w-[min(440px,92vw)] rounded-card border border-border bg-surface p-7 shadow-lift">
        <h2 className="font-display text-lg text-text">挑一个你的颜色</h2>
        <p className="mb-5 mt-1 text-sm text-muted">它会成为整个界面的强调色。随时能在设置里改。</p>

        <div className="mb-5 flex flex-wrap items-center gap-3">
          {ACCENT_PRESETS.map((c) => (
            <button
              key={c}
              aria-label={`选择 ${c}`}
              onClick={() => setAccent(c)}
              className="h-10 w-10 rounded-full transition"
              style={{
                background: c,
                outline: accent.toLowerCase() === c.toLowerCase() ? "3px solid rgb(var(--accent))" : "2px solid transparent",
                outlineOffset: 2,
              }}
            />
          ))}
          <label className="ml-1 inline-flex items-center gap-1.5 text-[13px] text-muted">
            自定义
            <input type="color" value={accent} onChange={(e) => setAccent(e.target.value)}
                   aria-label="自定义颜色" className="h-8 w-8 cursor-pointer border-0 bg-transparent p-0" />
          </label>
        </div>

        {/* 实时预览 */}
        <div className="flex items-center gap-3 rounded-input bg-surface-2 p-3.5">
          <span className="rounded-btn px-2.5 py-1 text-sm" style={{ background: "rgb(var(--accent) / 0.12)", color: "rgb(var(--accent))" }}>选中态</span>
          <button className="rounded-btn bg-accent px-3 py-1.5 text-sm text-white hover:bg-accent-hover">主按钮</button>
          <a className="text-sm" style={{ color: "rgb(var(--accent))" }} href="#" onClick={(e) => e.preventDefault()}>链接文字</a>
        </div>

        <div className="mt-6 flex justify-end gap-2.5">
          <button onClick={() => finish(ACCENT_PRESETS[0])}
                  className="rounded-btn border border-border px-3.5 py-2 text-sm text-muted hover:bg-surface-2 hover:text-text">
            用默认
          </button>
          <button onClick={() => finish(accent)}
                  className="rounded-btn bg-accent px-4 py-2 text-sm text-white hover:bg-accent-hover">
            就用这个
          </button>
        </div>
      </div>
    </div>
  );
}
