"""backend.org_admin — org_core 的只读查询(管理界面用)+ 写操作走 OrgService。

只读用 repo.db(SqliteRepos 暴露的连接)做列表查询,不改 org_core 核心。
写操作(建节点/派岗等)直接调 OrgService,鉴权与审计已在其中。
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional


def build_tree(repo, tenant_id: str, root_id: str) -> Optional[Dict[str, Any]]:
    node = repo.get_node(tenant_id, root_id)
    if not node:
        return None
    return {
        "id": node.id, "name": node.name, "type": node.type.value,
        "children": [build_tree(repo, tenant_id, c.id)
                     for c in repo.children(tenant_id, node.id)],
    }


def list_roles(repo, tenant_id: str) -> List[Dict[str, Any]]:
    rows = repo.db.execute(
        "SELECT id,name,perm_keys FROM roles WHERE tenant_id=?", (tenant_id,)).fetchall()
    return [{"id": r["id"], "name": r["name"],
             "perms": [p for p in (r["perm_keys"] or "").split(",") if p]} for r in rows]


def list_users(repo, tenant_id: str) -> List[Dict[str, Any]]:
    """列真人 + 其子账号(grant=岗位@组织节点)。"""
    urows = repo.db.execute(
        "SELECT id,display_name,kind,status FROM users WHERE tenant_id=?", (tenant_id,)).fetchall()
    # 预取岗位名、节点名
    rolemap = {r["id"]: r["name"] for r in repo.db.execute(
        "SELECT id,name FROM roles WHERE tenant_id=?", (tenant_id,)).fetchall()}
    nodemap = {n["id"]: n["name"] for n in repo.db.execute(
        "SELECT id,name FROM org_nodes WHERE tenant_id=?", (tenant_id,)).fetchall()}
    out = []
    for u in urows:
        grows = repo.db.execute(
            "SELECT id,role_id,org_node_id,label,active,is_default FROM grants "
            "WHERE tenant_id=? AND user_id=?", (tenant_id, u["id"])).fetchall()
        grants = [{
            "id": g["id"], "role": rolemap.get(g["role_id"], "?"),
            "node": nodemap.get(g["org_node_id"], "?"), "node_id": g["org_node_id"],
            "label": g["label"], "active": bool(g["active"]), "is_default": bool(g["is_default"]),
        } for g in grows]
        out.append({"id": u["id"], "name": u["display_name"], "kind": u["kind"],
                    "status": u["status"], "grants": grants})
    return out


def flat_nodes(repo, tenant_id: str) -> List[Dict[str, str]]:
    rows = repo.db.execute(
        "SELECT id,name,parent_id,type FROM org_nodes WHERE tenant_id=?", (tenant_id,)).fetchall()
    return [{"id": r["id"], "name": r["name"], "parent_id": r["parent_id"] or "", "type": r["type"]} for r in rows]
