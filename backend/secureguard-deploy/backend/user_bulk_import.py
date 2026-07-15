"""backend.user_bulk_import — 组织架构/员工 Excel·CSV 批量导入(接现有 auth)。

管理员上传表格 → 逐行建用户(手机号/角色/部门),初始密码可表内给或自动生成。
角色白名单校验(防越权造 admin);单行失败不影响整批;返回报告(含初始密码,供分发)。
纯 stdlib(CSV);xlsx 由端点用 openpyxl 读成行后调本模块。可离线测。
"""
from __future__ import annotations

import csv
import io
import secrets
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# 允许批量导入指定的角色(防止从表格造出 admin/受限管理员/审计员)
IMPORTABLE_ROLES = {"user", "developer", "department_admin"}


@dataclass
class ImportReport:
    created: List[Dict[str, str]] = field(default_factory=list)   # {phone, role, dept_id, init_password}
    skipped: List[Dict[str, str]] = field(default_factory=list)   # {phone, reason}
    failed: List[Dict[str, str]] = field(default_factory=list)    # {row, reason}
    def summary(self): return {"created": len(self.created), "skipped": len(self.skipped), "failed": len(self.failed)}
    def public(self): return {"summary": self.summary(), "created": self.created, "skipped": self.skipped, "failed": self.failed}


def _gen_password() -> str:
    return "Aa" + secrets.token_hex(3)   # 8位初始密码,导入后提示改密


def import_users(
    rows: List[Dict[str, Any]],
    *,
    register_fn: Callable[[str, str, str, Optional[str]], str],   # (phone, pwd, role, dept_id) -> uid
    exists_fn: Callable[[str], bool],                            # phone -> 已存在?
    default_role: str = "user",
) -> ImportReport:
    rep = ImportReport()
    for i, row in enumerate(rows, 1):
        phone = str(row.get("phone") or row.get("手机号") or "").strip()
        role = str(row.get("role") or row.get("角色") or default_role).strip() or default_role
        dept = str(row.get("dept_id") or row.get("部门") or "").strip() or None
        pwd = str(row.get("password") or row.get("初始密码") or "").strip()
        try:
            import re
            if not re.fullmatch(r"1[3-9]\d{9}", phone):
                rep.failed.append({"row": str(i), "reason": f"手机号无效: {phone or '空'}"}); continue
            if role not in IMPORTABLE_ROLES:
                rep.failed.append({"row": str(i), "reason": f"不允许导入角色: {role}(仅 {sorted(IMPORTABLE_ROLES)})"}); continue
            if exists_fn(phone):
                rep.skipped.append({"phone": phone, "reason": "手机号已存在"}); continue
            init_pwd = pwd if len(pwd) >= 6 else _gen_password()
            register_fn(phone, init_pwd, role, dept)
            rep.created.append({"phone": phone, "role": role, "dept_id": dept or "", "init_password": init_pwd})
        except Exception as e:
            rep.failed.append({"row": str(i), "reason": str(e)[:200]})
    return rep


def import_users_csv(csv_text: str, **kw) -> ImportReport:
    return import_users(list(csv.DictReader(io.StringIO(csv_text))), **kw)


def template_csv() -> str:
    return ("phone,role,dept_id,password\n"
            "13800001111,user,d1,\n"
            "13800002222,department_admin,d1,\n"
            "# role 可选: user/developer/department_admin;dept_id 为部门标识;password 留空则自动生成\n")
