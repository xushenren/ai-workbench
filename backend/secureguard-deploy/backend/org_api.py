"""org_api.py — 组织权限管理 REST 接口"""
from __future__ import annotations
import os, uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from org_core import OrgService, SqliteRepos, P, authorize
from org_core.permissions import ALL_PERMS
from org_core.models import NodeType, User, UserKind, UserStatus, Role as OrgRole, Grant

router = APIRouter(prefix="/v1/org")
_repo = SqliteRepos(os.getenv("ORG_DB", "/data/org_core.db"))
svc = OrgService(_repo)

_seed_grants: dict[str, str] = {}

def _ensure_seed(tid: str) -> str:
    """确保租户有种子管理员，返回 grant_id"""
    if tid in _seed_grants:
        return _seed_grants[tid]
    t = _repo.get_tenant(tid)
    if not t:
        raise HTTPException(404, "租户不存在")
    roots = _repo.children(tid, None)
    if not roots:
        raise HTTPException(500, "租户无根节点")
    root = roots[0]
    # 创建种子管理员
    u = User(uuid.uuid4().hex, tid, UserKind.INTERNAL, UserStatus.ACTIVE, "平台管理员")
    r = OrgRole(uuid.uuid4().hex, tid, "平台管理员", ALL_PERMS)
    g, _ = svc.seed_admin(tid, user=u, role=r, node_id=root.id)
    _seed_grants[tid] = g.id
    return g.id


def _all_nodes(tid: str) -> list:
    result = []
    roots = _repo.children(tid, None)
    for r in roots:
        result.append(r)
        _collect(tid, r.id, result)
    return result

def _collect(tid: str, pid: str, acc: list):
    for k in _repo.children(tid, pid):
        acc.append(k)
        _collect(tid, k.id, acc)


# --- schemas ---
class TenantIn(BaseModel):
    name: str
    root_name: str = "集团总部"

class NodeIn(BaseModel):
    parent_id: str
    name: str
    node_type: str = "department"

class UserIn(BaseModel):
    home_node_id: str
    name: str
    phone: str = ""
    external_id: str = ""

class RoleIn(BaseModel):
    at_node_id: str
    name: str
    perm_keys: list[str]

class GrantIn(BaseModel):
    user_id: str
    role_id: str
    org_node_id: str

class AuthzIn(BaseModel):
    grant_id: str
    action: str
    target_node_id: str | None = None


# --- routes ---
@router.post("/tenants")
def bootstrap(body: TenantIn):
    t, root = svc.bootstrap_tenant(body.name, body.root_name)
    gid = _ensure_seed(t.id)
    return {"tenant": t.__dict__, "root_node": root.__dict__, "admin_grant_id": gid}

@router.get("/tenants/{tid}")
def get_tenant(tid: str):
    t = _repo.get_tenant(tid)
    if not t: raise HTTPException(404)
    return t.__dict__

@router.post("/tenants/{tid}/nodes")
def create_node(tid: str, body: NodeIn):
    gid = _ensure_seed(tid)
    n = svc.create_node(tid, gid, parent_id=body.parent_id,
                        display_name=body.name, type=NodeType(body.node_type))
    return n.__dict__

@router.get("/tenants/{tid}/tree")
def get_tree(tid: str):
    nodes = _all_nodes(tid)
    node_map = {n.id: {**n.__dict__, "children": []} for n in nodes}
    roots = []
    for n in nodes:
        if n.parent_id and n.parent_id in node_map:
            node_map[n.parent_id]["children"].append(node_map[n.id])
        else:
            roots.append(node_map[n.id])
    return {"tenant_id": tid, "tree": roots}

@router.post("/tenants/{tid}/users")
def add_user(tid: str, body: UserIn):
    gid = _ensure_seed(tid)
    u = svc.add_user(tid, gid, home_node_id=body.home_node_id,
                     display_name=body.name, phone=body.phone, external_id=body.external_id)
    return u.__dict__

@router.get("/tenants/{tid}/users")
def list_users(tid: str):
    return [u.__dict__ for u in _repo._list_users(tid)]

@router.post("/tenants/{tid}/roles")
def define_role(tid: str, body: RoleIn):
    gid = _ensure_seed(tid)
    r = svc.define_role(tid, gid, at_node_id=body.at_node_id,
                        display_name=body.name, perm_keys=set(body.perm_keys))
    return r.__dict__

@router.get("/tenants/{tid}/roles")
def list_roles(tid: str):
    return [r.__dict__ for r in _repo._list_roles(tid)]

@router.post("/tenants/{tid}/grants")
def grant_role(tid: str, body: GrantIn):
    gid = _ensure_seed(tid)
    g = svc.grant_role(tid, gid, user_id=body.user_id,
                       role_id=body.role_id, org_node_id=body.org_node_id)
    return g.__dict__

@router.get("/tenants/{tid}/grants")
def list_grants(tid: str):
    return [g.__dict__ for g in _repo._list_grants(tid)]

@router.post("/tenants/{tid}/authz/check")
def check_permission(tid: str, body: AuthzIn):
    ok, reason = authorize(_repo, tid, body.grant_id, body.action, body.target_node_id)
    return {"allowed": ok, "reason": reason}

@router.get("/tenants/{tid}/permissions")
def list_permissions(tid: str):
    return {"perms": sorted(ALL_PERMS)}
