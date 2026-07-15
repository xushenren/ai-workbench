// 主题模式偏好:亮/暗/跟随系统,localStorage 记住
type Mode = "light" | "dark" | "system";
const KEY_MODE = "pref_theme";

export function applyTheme(mode: Mode) {
  const dark = mode === "dark" || (mode === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  localStorage.setItem(KEY_MODE, mode);
}

export function getMode(): Mode {
  return (localStorage.getItem(KEY_MODE) as Mode) || "system";
}

export function initTheme() {
  applyTheme(getMode());
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (getMode() === "system") applyTheme("system");
  });
}
