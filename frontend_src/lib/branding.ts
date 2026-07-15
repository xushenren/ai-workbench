// branding.ts — 全局应用品牌:启动时拉取并写入 document.title / favicon / 强调色变量。
import { api } from "@/lib/api";

export interface Brand {
  platform_name: string; logo_url: string; favicon_url: string;
  brand_color: string; brand_color_dark: string; lock_accent: boolean; login_tagline: string;
}

export function applyBranding(b: Brand) {
  if (b.platform_name) document.title = b.platform_name;
  if (b.brand_color) document.documentElement.style.setProperty("--brand", b.brand_color);
  if (b.brand_color) document.documentElement.style.setProperty("--accent", b.brand_color);
  if (b.favicon_url) {
    let link = document.querySelector<HTMLLinkElement>("link[rel~='icon']");
    if (!link) { link = document.createElement("link"); link.rel = "icon"; document.head.appendChild(link); }
    link.href = b.favicon_url;
  }
}

export async function loadBranding(): Promise<Brand | null> {
  try { const b = await api.getBranding(); applyBranding(b); return b; } catch { return null; }
}
