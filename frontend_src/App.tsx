// 路由 + 鉴权守卫。未登录访问受保护页 → 跳 /login；/login、/register 公开。
// 角色守卫：roles 指定后，非该角色 → 跳 /chat（职责分离：用户管理=admin、审计=auditor）。
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useState, type ReactNode } from "react";
import { Layout } from "@/components/Layout";
import { ChatView } from "@/pages/ChatView";
import { AgentStore } from "@/pages/AgentStore";
import { KnowledgeBaseView } from "@/pages/KnowledgeBaseView";
import { AdminPanel } from "@/pages/AdminPanel";
import { OrgAdminView } from "@/pages/OrgAdminView";
import { AdminBrandingPanel } from "@/pages/AdminBrandingPanel";
import { ModelsView } from "@/pages/ModelsView";
import { UserAdminView } from "@/pages/UserAdminView";
import { AuditView } from "@/pages/AuditView";
import { EvolutionView } from "@/pages/EvolutionView";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { useAuthStore } from "@/stores/useAuthStore";
import { FirstRunColorPicker } from "@/components/FirstRunColorPicker";
import { BrandingProvider } from "@/components/BrandingProvider";
import { isOnboarded } from "@/lib/accentTheme";
import type { Role } from "@/types";

/** 受保护路由：未登录 → /login；指定 roles 后非该角色 → /chat。 */
function RequireAuth({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const user = useAuthStore((s) => s.user);
  const authed = useAuthStore((s) => s.isAuthed());
  if (!authed) return <Navigate to="/login" replace />;
  if (roles && (!user || !roles.includes(user.role))) return <Navigate to="/chat" replace />;
  return <Layout>{children}</Layout>;
}

export default function App() {
  const authed = useAuthStore((s) => s.isAuthed());
  const [showPicker, setShowPicker] = useState(() => !isOnboarded());
  return (
    <BrowserRouter basename="/app">
      {authed && showPicker && <FirstRunColorPicker onDone={() => setShowPicker(false)} />}
      <BrandingProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/chat" element={<RequireAuth><ChatView /></RequireAuth>} />
        <Route path="/agents" element={<RequireAuth><AgentStore /></RequireAuth>} />
        <Route path="/kb" element={<RequireAuth><KnowledgeBaseView /></RequireAuth>} />
        <Route path="/admin" element={<RequireAuth roles={["admin"]}><AdminPanel /></RequireAuth>} />
        <Route path="/org" element={<RequireAuth roles={["admin"]}><OrgAdminView /></RequireAuth>} />
        <Route path="/users" element={<RequireAuth roles={["admin"]}><UserAdminView /></RequireAuth>} />
        <Route path="/models" element={<RequireAuth roles={["admin"]}><ModelsView /></RequireAuth>} />
        <Route path="/branding" element={<RequireAuth roles={["admin"]}><AdminBrandingPanel /></RequireAuth>} />
        <Route path="/audit" element={<RequireAuth roles={["auditor"]}><AuditView /></RequireAuth>} />
        <Route path="/evolution" element={<RequireAuth roles={["admin"]}><EvolutionView /></RequireAuth>} />
        {/* 默认：已登录→/chat，未登录→/login */}
        <Route path="*" element={<Navigate to={authed ? "/chat" : "/login"} replace />} />
      </Routes>
      </BrandingProvider>
    </BrowserRouter>
  );
}
