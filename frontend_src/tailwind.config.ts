import type { Config } from "tailwindcss";

/** 颜色全部映射到 CSS 变量（见 index.css 的 :root / .dark），
 *  一套类名两套主题。rgb(var(--x) / <alpha>) 支持透明度。 */
const color = (v: string) => `rgb(var(${v}) / <alpha-value>)`;

export default {
  darkMode: "class",
  content: ["./index.html", "./pages/**/*.tsx", "./components/**/*.tsx", "./stores/*.ts", "./lib/*.ts", "./App.tsx", "./main.tsx"],
  theme: {
    extend: {
      colors: {
        bg: color("--bg"),
        surface: color("--surface"),
        "surface-2": color("--surface-2"),
        border: color("--border"),
        text: color("--text"),
        muted: color("--muted"),
        accent: color("--accent"),
        "accent-hover": color("--accent-hover"),
        warning: color("--warning"),
        success: color("--success"),
      },
      fontFamily: {
        serif: ['Newsreader', 'Georgia', 'Songti SC', 'serif'],
        sans: ['Inter', 'system-ui', '-apple-system', '"Noto Sans SC"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      borderRadius: { card: "12px", btn: "8px", input: "12px" },
      boxShadow: {
        soft: "0 1px 2px rgb(0 0 0 / 0.04), 0 2px 8px rgb(0 0 0 / 0.04)",
        lift: "0 2px 4px rgb(0 0 0 / 0.06), 0 8px 24px rgb(0 0 0 / 0.08)",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0", transform: "translateY(4px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        "slide-in": { from: { opacity: "0", transform: "translateX(8px)" }, to: { opacity: "1", transform: "translateX(0)" } },
        "soft-pulse": { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.45" } },
        "caret-blink": { "0%,100%": { opacity: "1" }, "50%": { opacity: "0" } },
      },
      animation: {
        "fade-in": "fade-in 0.28s ease both",
        "slide-in": "slide-in 0.3s ease both",
        "soft-pulse": "soft-pulse 1.6s ease-in-out infinite",
        "caret-blink": "caret-blink 1s step-end infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
