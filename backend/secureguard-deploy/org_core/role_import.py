"""
org_core.role_import — 岗位批量导入(标准模板:Excel/CSV → 岗位+权限位)。

模板列:  role_name | perm_keys(分号或逗号分隔)
逐行:校验权限位合法 → 建 Role。未知权限位整行报错(显式失败,不静默跳过)。

xlsx 解析是薄适配:用 openpyxl 把每行读成 dict 再调 import_roles 即可(见 README)。
本模块只依赖 stdlib(csv),保证可离线测。
"""
from __future__ import annotations

import csv
import io
import uuid
from typing import Iterable

from .models import Role
from .permissions import ALL_PERMS, validate_perm_keys
from .repository import Repos


def _split_perms(cell: str) -> frozenset[str]:
    parts = [p.strip() for p in cell.replace(";", ",").replace("；", ",").replace("，", ",").split(",")]
    return frozenset(p for p in parts if p)


def import_roles(repo: Repos, tenant_id: str, rows: Iterable[dict]) -> list[Role]:
    """rows: 每行 {'role_name':..., 'perm_keys':'kb.read;kb.promote'}。返回已建岗位。"""
    created: list[Role] = []
    for i, row in enumerate(rows, 1):
        name = (row.get("role_name") or row.get("岗位") or "").strip()
        if not name:
            raise ValueError(f"第 {i} 行缺少 role_name")
        perms = validate_perm_keys(_split_perms(row.get("perm_keys") or row.get("权限位") or ""))
        r = Role(uuid.uuid4().hex, tenant_id, name, perms)
        repo.add_role(r)
        created.append(r)
    return created


def import_roles_csv(repo: Repos, tenant_id: str, csv_text: str) -> list[Role]:
    return import_roles(repo, tenant_id, csv.DictReader(io.StringIO(csv_text)))


def template_csv() -> str:
    """生成标准导入模板(含全部可用权限位说明行)。"""
    header = "role_name,perm_keys\n"
    example = "项目部经理,kb.read;agent.create_private\n专家,kb.read;kb.write_private;kb.promote\n"
    legend = "# 可用权限位: " + " ".join(sorted(ALL_PERMS)) + "\n"
    return header + example + legend
