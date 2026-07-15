"""backend.org_excel_import — 多级组织架构 Excel 导入(接 org_core)。

两张表:
  组织表 org:   节点名 | 上级节点 | 类型(company/department/project/team)
  人员表 people: 手机号 | 姓名 | 岗位 | 所属节点 | 初始密码(可空)
流程:先建多级树(多趟拓扑,按名去重)→ 建登录账号+org_core真人 → 按岗位+节点派任职(grant)。
写操作经 OrgService(受管理子树约束+审计)。支持 dry_run 预演(只出报告不落库)。
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from org_core import NodeType, PermissionDenied

_TYPE = {"公司": "company", "子公司": "company", "部门": "department",
         "项目部": "project", "班组": "team",
         "company": "company", "department": "department", "project": "project", "team": "team"}


@dataclass
class OrgImportReport:
    nodes_created: List[str] = field(default_factory=list)
    nodes_reused: List[str] = field(default_factory=list)
    users_created: List[Dict[str, str]] = field(default_factory=list)   # {phone, init_password}
    grants_created: List[str] = field(default_factory=list)              # "姓名@岗位@节点"
    errors: List[Dict[str, str]] = field(default_factory=list)          # {item, reason}
    dry_run: bool = False
    def summary(self):
        return {"nodes_created": len(self.nodes_created), "nodes_reused": len(self.nodes_reused),
                "users_created": len(self.users_created), "grants_created": len(self.grants_created),
                "errors": len(self.errors), "dry_run": self.dry_run}
    def public(self): return {"summary": self.summary(), **self.__dict__}


def _gen_pwd() -> str: return "Aa" + secrets.token_hex(3)


def import_org(
    org_rows: List[Dict[str, Any]],
    people_rows: List[Dict[str, Any]],
    *,
    svc, repo, tenant_id: str, root_id: str, importer_grant_id: str,
    register_fn: Callable[[str, str, str, Optional[str]], str],   # auth 建登录账号 -> user_id
    provision_person: Callable[[str], str],                       # user_id -> org_core person_id
    exists_phone: Callable[[str], bool],
    dry_run: bool = False,
) -> OrgImportReport:
    rep = OrgImportReport(dry_run=dry_run)

    # 现有节点名→id(去重/复用);岗位名→id
    name2node: Dict[str, str] = {}
    for n in repo.db.execute("SELECT id,name FROM org_nodes WHERE tenant_id=?", (tenant_id,)).fetchall():
        name2node[n["name"]] = n["id"]
    name2role: Dict[str, str] = {}
    for r in repo.db.execute("SELECT id,name FROM roles WHERE tenant_id=?", (tenant_id,)).fetchall():
        name2role[r["name"]] = r["id"]

    # ---------- 1) 建多级树(多趟:父就绪才建子)----------
    pending = []
    for row in org_rows:
        nm = str(row.get("节点名") or row.get("name") or "").strip()
        parent = str(row.get("上级节点") or row.get("parent") or "").strip()
        typ = _TYPE.get(str(row.get("类型") or row.get("type") or "department").strip(), "department")
        if not nm:
            continue
        if nm in name2node:
            rep.nodes_reused.append(nm); continue
        pending.append({"name": nm, "parent": parent, "type": typ})

    progress = True
    while pending and progress:
        progress = False
        for item in pending[:]:
            parent = item["parent"]
            parent_id = root_id if (not parent or parent in ("总部", "根", "root")) else name2node.get(parent)
            if parent_id is None:
                continue  # 父还没建,下一趟
            try:
                if not dry_run:
                    n = svc.create_node(tenant_id, importer_grant_id, parent_id=parent_id,
                                        type=NodeType(item["type"]), name=item["name"])
                    name2node[item["name"]] = n.id
                else:
                    name2node[item["name"]] = "dry_" + item["name"]
                rep.nodes_created.append(item["name"])
            except PermissionDenied as e:
                rep.errors.append({"item": f"节点 {item['name']}", "reason": str(e)})
            except Exception as e:
                rep.errors.append({"item": f"节点 {item['name']}", "reason": str(e)[:120]})
            pending.remove(item); progress = True
    for item in pending:  # 父始终未出现
        rep.errors.append({"item": f"节点 {item['name']}", "reason": f"上级『{item['parent']}』不存在"})

    # ---------- 2) 建人 + 派任职(一人多行=多任职)----------
    person_cache: Dict[str, str] = {}    # phone -> person_id
    import re
    for row in people_rows:
        phone = str(row.get("手机号") or row.get("phone") or "").strip()
        name = str(row.get("姓名") or row.get("name") or "").strip()
        role_name = str(row.get("岗位") or row.get("role") or "").strip()
        node_name = str(row.get("所属节点") or row.get("node") or "").strip()
        pwd = str(row.get("初始密码") or row.get("password") or "").strip()
        try:
            if not re.fullmatch(r"1[3-9]\d{9}", phone):
                rep.errors.append({"item": f"人员 {name or phone}", "reason": "手机号无效"}); continue
            role_id = name2role.get(role_name)
            if not role_id:
                rep.errors.append({"item": f"{name}@{role_name}", "reason": f"岗位『{role_name}』不存在,请先在岗位管理创建"}); continue
            node_id = name2node.get(node_name)
            if not node_id:
                rep.errors.append({"item": f"{name}@{node_name}", "reason": f"节点『{node_name}』不存在"}); continue

            # 建登录账号 + org_core 真人(每个 phone 一次)
            if phone not in person_cache:
                if not exists_phone(phone):
                    init = pwd if len(pwd) >= 6 else _gen_pwd()
                    if not dry_run:
                        uid = register_fn(phone, init, "user", None)
                        pid = provision_person(uid)
                    else:
                        pid = "dry_person_" + phone
                    rep.users_created.append({"phone": phone, "init_password": init})
                    person_cache[phone] = pid
                else:
                    # 已有账号:仍需拿到 person_id 派岗
                    person_cache[phone] = "existing_" + phone if dry_run else provision_person_by_phone(repo, tenant_id, phone, provision_person)
            person_id = person_cache[phone]

            # 派任职(grant)——经 OrgService,受管理子树约束
            if not dry_run:
                svc.grant_role(tenant_id, importer_grant_id, user_id=person_id, role_id=role_id,
                               org_node_id=node_id, label=f"{name}@{node_name}-{role_name}")
            rep.grants_created.append(f"{name}@{role_name}@{node_name}")
        except PermissionDenied as e:
            rep.errors.append({"item": f"{name}", "reason": str(e)})
        except Exception as e:
            rep.errors.append({"item": f"{name}", "reason": str(e)[:120]})
    return rep


def provision_person_by_phone(repo, tenant_id, phone, provision_person):
    """已有登录账号但需 person:用 display_name=phone 反查或新建。占位实现。"""
    row = repo.db.execute("SELECT id FROM users WHERE tenant_id=? AND display_name=?",
                          (tenant_id, phone)).fetchone()
    return row["id"] if row else provision_person(phone)
