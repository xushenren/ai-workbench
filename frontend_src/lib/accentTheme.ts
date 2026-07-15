// accentTheme.ts — 个人强调色:写入 /app 的 --accent / --accent-hover 变量并持久化。
// /app 颜色用"空格分隔 RGB 三元组"(配合 tailwind 的 rgb(var()/alpha)),这里把 #hex 转成三元组。

const KEY_ACCENT = "app.accent";
const KEY_ONBOARDED = "app.accent.onboarded";

export const ACCENT_PRESETS = [
  "#3B82D8", // Kun 蓝(默认)
  "#0F766E", // 青
  "#7C3AED", // 紫
  "#B4530A", // 琥珀
  "#BE123C", // 绛红
  "#1F2937", // 墨
];

function hexToTriple(hex: string): string {
  const h = hex.replace("#", "");
  const n = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const int = parseInt(n || "3b82d8", 16);
  return `${(int >> 16) & 255} ${(int >> 8) & 255} ${int & 255}`;
}

function darken(hex: string, amount = 0.12): string {
  const h = hex.replace("#", "");
  const n = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const int = parseInt(n, 16);
  const f = (x: number) => Math.max(0, Math.round(x * (1 - amount)));
  return `${f((int >> 16) & 255)} ${f((int >> 8) & 255)} ${f(int & 255)}`;
}

/** 立即把强调色写进 :root(全站生效)。不持久化,用于实时预览。 */
export function applyAccent(hex: string): void {
  const root = document.documentElement;
  root.style.setProperty("--accent", hexToTriple(hex));
  root.style.setProperty("--accent-hover", darken(hex));
}

/** 保存为个人强调色并标记已完成引导。 */
export function saveAccent(hex: string): void {
  applyAccent(hex);
  try {
    localStorage.setItem(KEY_ACCENT, hex);
    localStorage.setItem(KEY_ONBOARDED, "1");
  } catch { /* 隐私模式忽略 */ }
}

/** 应用启动时调用:有保存值就应用(否则用 index.css 里的 Kun 默认)。 */
export function bootAccent(): void {
  try {
    const saved = localStorage.getItem(KEY_ACCENT);
    if (saved) applyAccent(saved);
  } catch { /* ignore */ }
}

export function isOnboarded(): boolean {
  try { return localStorage.getItem(KEY_ONBOARDED) === "1"; } catch { return true; }
}

export function getSavedAccent(): string {
  try { return localStorage.getItem(KEY_ACCENT) || ACCENT_PRESETS[0]; } catch { return ACCENT_PRESETS[0]; }
}
