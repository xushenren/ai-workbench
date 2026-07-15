// OrgAdminView.tsx — 组织权限管理(org_core 显形)。仅管理员。
// 左:组织树(可建子部门)。右:人员及其子账号(任职),可建岗位、派岗。
import { useEffect, useState } from "react";
import { Plus, Building2, Users, Shield, UploadCloud, Loader2, ChevronRight } from "lucide-react";
import { Card, Button, Badge } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { OrgImportPanel } from "@/pages/OrgImportPanel";

interface TreeNode { id: string; name: string; type: string; children: TreeNode[] }
interface Grant { id: string; role: string; node: string; node_id: string; label: string; active: boolean; is_default: boolean }
interface OrgUser { id: string; name: string; kind: string; status: string; grants: Grant[] }
interface RoleRec { id: string; name: string; perms: string[] }
interface NodeFlat { id: string; name: string; parent_id: string; type: string }

export function OrgAdminView() {
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [users, setUsers] = useState<OrgUser[]>([]);
  const [roles, setRoles] = useState<RoleRec[]>([]);
  const [nodes, setNodes] = useState<NodeFlat[]>([]);
  const [perms, setPerms] = useState<string[]>([]);
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const [tab, setTab] = useState<"tree" | "users" | "roles" | "import">("tree");

  const note = (ok: boolean, t: string) => { setMsg({ ok, t }); setTimeout(() => setMsg(null), 2600); };
  const reload = () => {
    api.orgTree().then(setTree).catch(() => {});
    api.orgUsers().then(setUsers).catch(() => {});
    api.orgRoles().then(setRoles).catch(() => {});
    api.orgNodes().then(setNodes).catch(() => {});
  };
  useEffect(() => { reload(); api.orgPerms().then(setPerms).catch(() => {}); }, []);

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="mb-1 font-display text-xl font-semibold">组织与权限管理</h1>
      <p className="mb-4 text-sm text-muted">多级组织树、岗位(权限位组合)、人员任职(子账号)。操作受管理子树约束。</p>

      <div className="mb-4 flex gap-1.5">
        {([["tree", "组织树", Building2], ["users", "人员与任职", Users], ["roles", "岗位", Shield], ["import", "导入", UploadCloud]] as const).map(([k, label, Icon]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`flex items-center gap-1.5 rounded-btn px-3 py-1.5 text-sm ${tab === k ? "bg-surface-2 text-text" : "text-muted hover:text-text"}`}>
            <Icon size={15} /> {label}
          </button>
        ))}
        {msg && <span className={`ml-auto self-center text-xs ${msg.ok ? "text-accent" : "text-red-500"}`}>{msg.t}</span>}
      </div>

      {tab === "tree" && <TreePanel tree={tree} nodes={nodes} onChange={reload} note={note} />}
      {tab === "users" && <UsersPanel users={users} roles={roles} nodes={nodes} onChange={reload} note={note} />}
      {tab === "roles" && <RolesPanel roles={roles} nodes={nodes} perms={perms} onChange={reload} note={note} />}
      {tab === "import" && <OrgImportPanel />}
    </div>
  );
}

/* ---------- 组织树 ---------- */
function TreePanel({ tree, nodes, onChange, note }: any) {
  const [parentId, setParentId] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState("department");
  const [busy, setBusy] = useState(false);

  const create = async () => {
    if (!parentId || !name.trim()) { note(false, "选上级节点并填名称"); return; }
    setBusy(true);
    try { await api.orgCreateNode({ parent_id: parentId, name: name.trim(), type }); setName(""); onChange(); note(true, "节点已创建"); }
    catch (e: any) { note(false, e.message); } finally { setBusy(false); }
  };

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card className="p-4">
        <div className="mb-2 text-sm font-medium">组织结构</div>
        {tree ? <TreeNodeRow node={tree} depth={0} /> : <div className="text-sm text-muted">加载中…</div>}
      </Card>
      <Card className="p-4">
        <div className="mb-3 text-sm font-medium">新建子部门 / 项目部</div>
        <label className="mb-1 block text-xs text-muted">上级节点</label>
        <select value={parentId} onChange={(e) => setParentId(e.target.value)} className={inp}>
          <option value="">选择上级…</option>
          {nodes.map((n: NodeFlat) => <option key={n.id} value={n.id}>{n.name}</option>)}
        </select>
        <label className="mb-1 mt-2 block text-xs text-muted">类型</label>
        <select value={type} onChange={(e) => setType(e.target.value)} className={inp}>
          <option value="company">子公司</option><option value="department">部门</option>
          <option value="project">项目部</option><option value="team">班组</option>
        </select>
        <label className="mb-1 mt-2 block text-xs text-muted">名称</label>
        <input value={name} onChange={(e) => setName(e.target.value)} className={inp} placeholder="如 机电安装项目部" />
        <Button size="sm" onClick={create} disabled={busy} className="mt-3">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} 创建
        </Button>
      </Card>
    </div>
  );
}
function TreeNodeRow({ node, depth }: { node: TreeNode; depth: number }) {
  return (
    <div>
      <div className="flex items-center gap-1 py-1 text-sm" style={{ paddingLeft: depth * 16 }}>
        {depth > 0 && <ChevronRight size={12} className="text-muted" />}
        <span>{node.name}</span>
        <Badge>{({ company: "公司", department: "部门", project: "项目部", team: "班组" } as any)[node.type] || node.type}</Badge>
      </div>
      {node.children?.map((c) => <TreeNodeRow key={c.id} node={c} depth={depth + 1} />)}
    </div>
  );
}

/* ---------- 人员与任职(子账号) ---------- */
function UsersPanel({ users, roles, nodes, onChange, note }: any) {
  const [sel, setSel] = useState<string>("");
  const [roleId, setRoleId] = useState("");
  const [nodeId, setNodeId] = useState("");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);

  const assign = async () => {
    if (!sel || !roleId || !nodeId) { note(false, "选人、岗位、组织节点"); return; }
    setBusy(true);
    try { await api.orgGrant({ user_id: sel, role_id: roleId, org_node_id: nodeId, label }); setLabel(""); onChange(); note(true, "已派岗(新增任职/子账号)"); }
    catch (e: any) { note(false, e.message); } finally { setBusy(false); }
  };

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card className="max-h-[60vh] overflow-y-auto p-4">
        <div className="mb-2 text-sm font-medium">人员({users.length})</div>
        {users.map((u: OrgUser) => (
          <div key={u.id} className={`mb-2 rounded-md border p-2 ${sel === u.id ? "border-accent" : "border-border"}`} onClick={() => setSel(u.id)} role="button">
            <div className="flex items-center gap-2 text-sm">
              <span className="font-medium">{u.name}</span>
              <Badge>{u.kind === "external" ? "外部" : "内部"}</Badge>
              {u.status !== "active" && <span className="text-xs text-red-500">已停用</span>}
            </div>
            {u.grants.map((g) => (
              <div key={g.id} className="mt-1 flex items-center gap-1.5 text-xs text-muted">
                <span className="rounded bg-surface-2 px-1.5 py-0.5">{g.role} @ {g.node}</span>
                {g.is_default && <span className="text-accent">默认</span>}
                {!g.active && <span className="text-red-500">停用</span>}
              </div>
            ))}
          </div>
        ))}
      </Card>
      <Card className="p-4">
        <div className="mb-3 text-sm font-medium">派岗 / 加任职(子账号)</div>
        <p className="mb-2 text-xs text-muted">{sel ? `已选:${users.find((u: OrgUser) => u.id === sel)?.name}` : "先在左侧点选一个人"}</p>
        <label className="mb-1 block text-xs text-muted">岗位</label>
        <select value={roleId} onChange={(e) => setRoleId(e.target.value)} className={inp}>
          <option value="">选岗位…</option>{roles.map((r: RoleRec) => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
        <label className="mb-1 mt-2 block text-xs text-muted">组织节点(作用域)</label>
        <select value={nodeId} onChange={(e) => setNodeId(e.target.value)} className={inp}>
          <option value="">选节点…</option>{nodes.map((n: NodeFlat) => <option key={n.id} value={n.id}>{n.name}</option>)}
        </select>
        <label className="mb-1 mt-2 block text-xs text-muted">任职名(可选)</label>
        <input value={label} onChange={(e) => setLabel(e.target.value)} className={inp} placeholder="如 张三@机电部-顾问" />
        <Button size="sm" onClick={assign} disabled={busy || !sel} className="mt-3">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} 派岗
        </Button>
      </Card>
    </div>
  );
}

/* ---------- 岗位(权限位组合) ---------- */
function RolesPanel({ roles, nodes, perms, onChange, note }: any) {
  const [name, setName] = useState("");
  const [atNode, setAtNode] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const toggle = (p: string) => setPicked((x) => x.includes(p) ? x.filter((y) => y !== p) : [...x, p]);

  const create = async () => {
    if (!name.trim() || !atNode || picked.length === 0) { note(false, "填名称、选节点、至少一个权限位"); return; }
    setBusy(true);
    try { await api.orgDefineRole({ at_node_id: atNode, name: name.trim(), perm_keys: picked }); setName(""); setPicked([]); onChange(); note(true, "岗位已创建"); }
    catch (e: any) { note(false, e.message); } finally { setBusy(false); }
  };

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card className="max-h-[60vh] overflow-y-auto p-4">
        <div className="mb-2 text-sm font-medium">已有岗位({roles.length})</div>
        {roles.map((r: RoleRec) => (
          <div key={r.id} className="mb-2 rounded-md border border-border p-2">
            <div className="text-sm font-medium">{r.name}</div>
            <div className="mt-1 flex flex-wrap gap-1">{r.perms.map((p) => <span key={p} className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted">{p}</span>)}</div>
          </div>
        ))}
      </Card>
      <Card className="p-4">
        <div className="mb-3 text-sm font-medium">新建岗位(权限位组合)</div>
        <label className="mb-1 block text-xs text-muted">岗位名</label>
        <input value={name} onChange={(e) => setName(e.target.value)} className={inp} placeholder="如 项目部经理" />
        <label className="mb-1 mt-2 block text-xs text-muted">定义于节点</label>
        <select value={atNode} onChange={(e) => setAtNode(e.target.value)} className={inp}>
          <option value="">选节点…</option>{nodes.map((n: NodeFlat) => <option key={n.id} value={n.id}>{n.name}</option>)}
        </select>
        <label className="mb-1 mt-2 block text-xs text-muted">权限位</label>
        <div className="flex max-h-40 flex-wrap gap-1.5 overflow-y-auto rounded-md border border-border p-2">
          {perms.map((p: string) => (
            <button key={p} onClick={() => toggle(p)} className={`rounded px-1.5 py-0.5 text-[11px] ${picked.includes(p) ? "bg-accent text-white" : "bg-surface-2 text-muted"}`}>{p}</button>
          ))}
        </div>
        <Button size="sm" onClick={create} disabled={busy} className="mt-3">{busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} 创建岗位</Button>
      </Card>
    </div>
  );
}

const inp = "w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm";
