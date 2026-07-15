// /users 用户管理（仅 admin）：列出用户、改角色、分配部门、审批部门申请。
// 解开"自助注册用户无部门→看不到部门资源"的死结。
import { useEffect, useMemo, useState } from "react";
import { Users, Check, X, Loader2, RefreshCw, Search, UserPlus, Trash2 } from "lucide-react";
import { Card, Badge, Button } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { AdminUser, DeptRequest, Role } from "@/types";

const ROLES: Role[] = ["user", "developer", "department_admin", "auditor", "admin"];
const ROLE_LABEL: Record<Role, string> = {
  user: "用户", developer: "开发者", department_admin: "部门管理员",
  auditor: "审计员", admin: "管理员",
};

export function UserAdminView() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [requests, setRequests] = useState<DeptRequest[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [savingId, setSavingId] = useState("");

  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ phone: "", password: "", role: "user" as Role, dept_id: "" });
  const [note, setNote] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return users;
    return users.filter((u) =>
      (u.phone ?? "").toLowerCase().includes(q) ||
      (u.id ?? "").toLowerCase().includes(q) ||
      (u.dept_id ?? "").toLowerCase().includes(q));
  }, [users, query]);

  const createUser = async () => {
    setErr(""); setNote("");
    if (!/^1[3-9]\d{9}$/.test(draft.phone.trim())) { setErr("手机号格式不正确"); return; }
    try {
      const res = await api.createUser(draft);
      setNote(`已创建 ${res.phone}${res.init_password ? ` · 初始密码 ${res.init_password}` : ""}`);
      setDraft({ phone: "", password: "", role: "user" as Role, dept_id: "" });
      setAdding(false); await load();
    } catch (e) { setErr((e as Error).message); }
  };

  const removeUser = async (u: AdminUser) => {
    if (!confirm(`删除用户 ${u.phone || u.id}？不可撤销。`)) return;
    setSavingId(u.id); setErr("");
    try { await api.deleteUser(u.id); await load(); }
    catch (e) { setErr((e as Error).message); } finally { setSavingId(""); }
  };

  const load = async () => {
    setLoading(true); setErr("");
    try {
      const [u, r] = await Promise.all([api.listUsers(), api.listDeptRequests()]);
      setUsers(u); setRequests(r);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { void load(); }, []);

  const changeRole = async (u: AdminUser, role: Role) => {
    setSavingId(u.id); setErr("");
    try { await api.setUserRole(u.id, role); await load(); }
    catch (e) { setErr((e as Error).message); }
    finally { setSavingId(""); }
  };

  const changeDept = async (u: AdminUser, dept: string) => {
    setSavingId(u.id); setErr("");
    try { await api.assignDepartment(u.id, dept || null); await load(); }
    catch (e) { setErr((e as Error).message); }
    finally { setSavingId(""); }
  };

  const handleReq = async (id: string, action: "approve" | "reject") => {
    setErr("");
    try { await api.handleDeptRequest(id, action); await load(); }
    catch (e) { setErr((e as Error).message); }
  };

  return (
    <div className="mx-auto h-full max-w-5xl overflow-y-auto px-6 py-8">
      <div className="flex items-center gap-2">
        <Users size={20} className="text-accent" />
        <h1 className="font-display text-2xl font-semibold tracking-tight">用户管理</h1>
        <Button variant="ghost" size="sm" className="ml-auto" onClick={load}>
          <RefreshCw size={14} /> 刷新
        </Button>
        <Button size="sm" onClick={() => setAdding(v=>!v)}>
          <UserPlus size={14} /> 新建用户
        </Button>
      </div>

      {err && <p className="mt-3 rounded-card border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">{err}</p>}
      {note && <p className="mt-3 rounded-card border border-accent/40 bg-accent/10 px-3 py-2 text-sm text-accent">{note}</p>}

      <div className="mt-3 flex items-center gap-2">
        <Search size={15} className="text-muted" />
        <input value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索用户…" autoFocus
          className="w-full rounded-input border border-border bg-surface-2 px-2.5 py-1.5 text-sm outline-none focus:border-accent/60" />
      </div>

      {/* 待审部门申请 */}
      {requests.length > 0 && (
        <Card className="mt-5 p-4">
          <h2 className="mb-2 text-sm font-medium">待审部门申请</h2>
          <div className="divide-y divide-border">
            {requests.map((r) => (
              <div key={r.id} className="flex items-center gap-3 py-2 text-sm">
                <code className="rounded bg-surface-2 px-1.5 py-0.5 text-xs">{r.user_id}</code>
                <span className="text-muted">申请加入</span>
                <Badge>{r.dept_id}</Badge>
                <div className="ml-auto flex gap-2">
                  <Button size="sm" onClick={() => handleReq(r.id, "approve")}><Check size={14} /> 通过</Button>
                  <Button size="sm" variant="outline" onClick={() => handleReq(r.id, "reject")}><X size={14} /> 拒绝</Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 用户表 */}
      <Card className="mt-5 overflow-hidden">
        <div className="grid grid-cols-[1.4fr_1fr_1.2fr_1fr] gap-2 border-b border-border bg-surface-2/50 px-4 py-2.5 text-xs font-medium text-muted">
          <span>用户 / 手机号</span><span>角色</span><span>部门</span><span></span>
        </div>
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted">
            <Loader2 size={16} className="animate-spin" /> 加载中…
          </div>
        ) : (
          filtered.map((u) => (
            <div key={u.id} className="grid grid-cols-[1.4fr_1fr_1.2fr_1fr] items-center gap-2 border-b border-border px-4 py-2.5 text-sm last:border-0">
              <div className="min-w-0">
                <div className="truncate font-medium">{u.id}</div>
                <div className="truncate text-xs text-muted">{u.phone}</div>
              </div>
              <select
                value={u.role}
                onChange={(e) => changeRole(u, e.target.value as Role)}
                className="rounded-input border border-border bg-surface-2 px-2 py-1.5 text-sm outline-none focus:border-accent/60"
              >
                {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
              </select>
              <input
                defaultValue={u.dept_id ?? ""}
                placeholder="无部门"
                onBlur={(e) => { if (e.target.value !== (u.dept_id ?? "")) void changeDept(u, e.target.value); }}
                className="w-full rounded-input border border-border bg-surface-2 px-2 py-1.5 text-sm outline-none focus:border-accent/60"
              />
              <div className="flex items-center gap-2">
                <button onClick={() => removeUser(u)} className="text-muted hover:text-red-500" title="删除用户">
                  <Trash2 size={14} />
                </button>
                {savingId === u.id ? <Loader2 size={14} className="animate-spin" /> : "改后失焦保存"}
              </div>
            </div>
          ))
        )}
      </Card>
      <p className="mt-2 text-xs text-muted">
        改角色即时生效（下次请求按新角色鉴权）。部门留空 = 无部门（仅可见公共资源）。
      </p>
    </div>
  );
}
