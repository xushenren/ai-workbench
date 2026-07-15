// BrandingProvider.tsx — 全局品牌上下文。包住 App;启动拉取并应用;给 header 用 <BrandLogo/> <BrandName/>。
import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { loadBranding, type Brand } from "@/lib/branding";

const Ctx = createContext<Brand | null>(null);
export const useBrand = () => useContext(Ctx);

export function BrandingProvider({ children }: { children: ReactNode }) {
  const [brand, setBrand] = useState<Brand | null>(null);
  useEffect(() => { loadBranding().then(setBrand); }, []);
  return <Ctx.Provider value={brand}>{children}</Ctx.Provider>;
}

// 放进顶栏 logo 位置:有自定义 logo 用图,否则回退默认(传 fallback)。
export function BrandLogo({ fallback, className = "h-7 w-7 rounded-md" }: { fallback?: ReactNode; className?: string }) {
  const b = useBrand();
  if (b?.logo_url) return <img src={b.logo_url} alt={b.platform_name || "logo"} className={className} />;
  return <>{fallback ?? null}</>;
}

// 放进顶栏平台名位置。
export function BrandName({ fallback = "AI 工作平台", className = "font-display text-sm font-semibold" }: { fallback?: string; className?: string }) {
  const b = useBrand();
  return <span className={className}>{b?.platform_name || fallback}</span>;
}
