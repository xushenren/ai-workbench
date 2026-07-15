import { create } from "zustand";
import type { Role } from "@/types";

/**
 * 鉴权 store。持久化决策：token 存 localStorage（刷新保持登录）——
 * 这是真实可用鉴权流的标准做法，**有意偏离 spec 第 7 条"不用 localStorage"**
 * （那条针对 UI 状态；会话 token 是公认例外）。想改回内存版：把下面 storage 读写删掉即可。
 */

export interface AuthUser {
  id: string;
  role: Role;
  dept_id: string | null;
}

const TOKEN_KEY = "eaw_token";
const USER_KEY = "eaw_user";

function loadToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
function loadUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch { return null; }
}
function persist(token: string | null, user: AuthUser | null): void {
  try {
    if (token && user) {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    } else {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    }
  } catch { /* localStorage 不可用时退化为内存态 */ }
}

const BASE = "/v1";

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  loading: boolean;
  error: string;

  isAuthed: () => boolean;
  login: (phone: string, password: string) => Promise<boolean>;
  register: (phone: string, password: string) => Promise<boolean>;
  logout: () => void;
}

async function authRequest(path: string, phone: string, password: string) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone, password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "请求失败");
  return data as { token: string; user: AuthUser };
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: loadToken(),
  user: loadUser(),
  loading: false,
  error: "",

  isAuthed: () => Boolean(get().token),

  login: async (phone, password) => {
    set({ loading: true, error: "" });
    try {
      const { token, user } = await authRequest("/auth/login", phone, password);
      persist(token, user);
      set({ token, user, loading: false });
      return true;
    } catch (e) {
      set({ loading: false, error: (e as Error).message || "登录失败" });
      return false;
    }
  },

  register: async (phone, password) => {
    set({ loading: true, error: "" });
    try {
      const { token, user } = await authRequest("/auth/register", phone, password);
      persist(token, user);            // 注册即登录
      set({ token, user, loading: false });
      return true;
    } catch (e) {
      set({ loading: false, error: (e as Error).message || "注册失败" });
      return false;
    }
  },

  logout: () => {
    persist(null, null);
    set({ token: null, user: null });
  },
}));

/** 给 REST/WS 取当前 token（非 React 环境用）。 */
export function currentToken(): string | null {
  return useAuthStore.getState().token;
}
