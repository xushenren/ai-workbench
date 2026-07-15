// 应用外壳：顶部导航 + 当前用户 + 退出 + 明暗切换 + 后端离线横幅。包裹所有受保护页面。
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { MessageSquare, Store, Library, Settings, Users, ShieldAlert, Sun, Moon, WifiOff, LogOut, Server, Building2 } from "lucide-react";
import { useUIStore } from "@/stores/useStore";
import { useAuthStore } from "@/stores/useAuthStore";
import { backendState, api } from "@/lib/api";
import { BrandLogo, BrandName } from "@/components/BrandingProvider";
import { ThemeMenu } from "@/components/ThemeMenu";
import { cn } from "@/lib/utils";

const ROLE_LABEL: Record<string, string> = {
  admin: "管理员", department_admin: "部门管理员", developer: "开发者", user: "用户", auditor: "审计员",
};

export function Layout({ children }: { children: ReactNode }) {
  const theme = useUIStore((s) => s.theme);
  const toggleTheme = useUIStore((s) => s.toggleTheme);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    void api.computeStatus().then(() => setOffline(!backendState.online));
  }, []);

  // 按角色显示导航：管理入口仅 admin 可见
  const nav = [
    { to: "/chat", label: "对话", Icon: MessageSquare },
    { to: "/agents", label: "智能体", Icon: Store },
    { to: "/kb", label: "知识库", Icon: Library },
    ...(user?.role === "admin" ? [
      { to: "/admin", label: "管理", Icon: Settings },
      { to: "/org", label: "组织", Icon: Building2 },
      { to: "/users", label: "用户", Icon: Users },
      { to: "/models", label: "模型", Icon: Server },
    ] : []),
    ...(user?.role === "auditor" ? [{ to: "/audit", label: "审计", Icon: ShieldAlert }] : []),
    { to: "/evolution", label: "进化", Icon: ShieldAlert },
  ];

  const doLogout = () => { logout(); navigate("/login"); };

  return (
    <div className="flex h-screen flex-col bg-bg text-text">
      {offline && (
        <div className="flex items-center justify-center gap-2 bg-warning/10 py-1.5 text-xs text-warning">
          <WifiOff size={13} /> 后端服务未连接 · 当前为演示数据
        </div>
      )}

      <header className="flex items-center gap-4 border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-2">
          <BrandLogo fallback={<div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent text-sm font-semibold text-white">元</div>} />
          <BrandName fallback="AI 工作平台" className="font-display text-lg font-semibold tracking-tight" />
        </div>

        <nav className="ml-4 flex items-center gap-1">
          {nav.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-1.5 rounded-btn px-3 py-1.5 text-sm transition-colors",
                  isActive ? "bg-surface-2 text-text" : "text-muted hover:text-text"
                )
              }
            >
              <Icon size={15} /> {label}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          {user && (
            <div className="flex items-center gap-2 rounded-btn bg-surface-2 px-2.5 py-1.5 text-xs">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent/15 text-accent">
                {user.id.slice(-2)}
              </span>
              <span className="text-muted">{ROLE_LABEL[user.role] ?? user.role}</span>
            </div>
          )}
          <ThemeMenu />
          <button
            onClick={toggleTheme}
            className="rounded-btn p-2 text-muted hover:bg-surface-2 hover:text-text"
            aria-label="切换明暗主题"
          >
            {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
          </button>
          {user && (
            <button
              onClick={doLogout}
              className="rounded-btn p-2 text-muted hover:bg-surface-2 hover:text-text"
              aria-label="退出登录"
              title="退出登录"
            >
              <LogOut size={16} />
            </button>
          )}
        </div>
      </header>

      <main className="min-h-0 flex-1">{children}</main>
    </div>
  );
}
