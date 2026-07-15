"""backend.md_version_store — 思考 MD 版本管理 + 回滚（进化系统地基）。

设计：版本库是真相源；"设为上线"时把该版内容【写回对应 .md 文件】，
于是现有热加载（load_profile 每次重读文件）完全不用改——回滚=把旧版写回文件。

每条 MD（main / domain-software / …）一条版本线：
  - 每版存档：完整内容 + 来源(manual/evolved) + parent + 评分 + 状态
  - 一个"上线指针"指向当前线上版
  - 操作：存版本 / 列版本 / 取版本 / 设为上线(=写回文件) / 回滚 / diff / 审计

独立有用：就算不进化，手动改 MD 也走版本线、能回滚。
纯 stdlib（json 持久化 + 内存），可离线测。进化范围仅 Plane-1，绝不碰 Plane-0（R-12）。
"""
from __future__ import annotations

import os
import json
import time
import uuid
import difflib
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any


def _now() -> float:
    return time.time()


@dataclass
class MdVersion:
    id: str
    md_name: str                         # "main" / "domain-software" / ...
    version: int                         # 该 md_name 下的递增版本号
    content: str                         # 完整 MD 文本
    origin: str = "manual"               # manual(人手改) / evolved(进化产生)
    parent: Optional[str] = None         # 从哪版来（进化时指向上一版）
    status: str = "archived"             # live / candidate / archived / rejected
    scores: Dict[str, Any] = field(default_factory=dict)   # {objective, human_winrate, sample_n}
    created_at: float = field(default_factory=_now)
    created_by: str = "system"
    note: str = ""

    def public(self) -> Dict[str, Any]:
        d = asdict(self)
        d["content_preview"] = (self.content[:200] + "…") if len(self.content) > 200 else self.content
        d["content_len"] = len(self.content)
        return d


class MdVersionStore:
    def __init__(self, thinking_dir: str, db_path: Optional[str] = None) -> None:
        # thinking_dir：.md 文件所在目录（设为上线时写回这里）
        self.thinking_dir = os.path.abspath(thinking_dir)
        self.db_path = db_path                       # json 持久化路径（None=纯内存）
        self._versions: Dict[str, MdVersion] = {}    # version_id -> MdVersion
        self._live: Dict[str, str] = {}              # md_name -> live version_id
        self._audit: List[Dict[str, Any]] = []
        self._load()

    # ---------- 持久化 ----------
    def _load(self) -> None:
        if self.db_path and os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._versions = {k: MdVersion(**v) for k, v in data.get("versions", {}).items()}
                self._live = data.get("live", {})
                self._audit = data.get("audit", [])
            except Exception:
                pass

    def _save(self) -> None:
        if not self.db_path:
            return
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump({
                    "versions": {k: asdict(v) for k, v in self._versions.items()},
                    "live": self._live, "audit": self._audit,
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _log(self, action: str, **kw: Any) -> None:
        self._audit.append({"ts": _now(), "action": action, **kw})

    # ---------- 初始化：从现有 .md 文件播种 v1 ----------
    def init_from_files(self, md_names: List[str]) -> None:
        """把现有 config/thinking/*.md 作为各自的 v1（live）纳入版本库。"""
        for name in md_names:
            if any(v.md_name == name for v in self._versions.values()):
                continue  # 已有版本线，不重复播种
            path = os.path.join(self.thinking_dir, f"{name}.md")
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            vid = self._new_version(name, content, origin="manual",
                                    created_by="seed", note="从现有文件播种 v1", status="live")
            self._live[name] = vid
            self._log("seed", md_name=name, version_id=vid)
        self._save()

    # ---------- 存新版本 ----------
    def _new_version(self, md_name: str, content: str, origin: str,
                     parent: Optional[str] = None, created_by: str = "system",
                     note: str = "", status: str = "candidate") -> str:
        existing = [v for v in self._versions.values() if v.md_name == md_name]
        ver_num = max([v.version for v in existing], default=0) + 1
        vid = f"{md_name}_v{ver_num}_{uuid.uuid4().hex[:6]}"
        self._versions[vid] = MdVersion(
            id=vid, md_name=md_name, version=ver_num, content=content,
            origin=origin, parent=parent, status=status,
            created_by=created_by, note=note,
        )
        return vid

    def save_version(self, md_name: str, content: str, origin: str = "manual",
                     parent: Optional[str] = None, created_by: str = "admin",
                     note: str = "") -> Dict[str, Any]:
        """存一个新版本（默认 candidate 状态，不自动上线）。"""
        vid = self._new_version(md_name, content, origin=origin, parent=parent,
                                created_by=created_by, note=note, status="candidate")
        self._log("save_version", md_name=md_name, version_id=vid, origin=origin)
        self._save()
        return self._versions[vid].public()

    # ---------- 设为上线（核心：写回 .md 文件，复用热加载）----------
    def set_live(self, version_id: str, by: str = "admin") -> Dict[str, Any]:
        v = self._versions.get(version_id)
        if not v:
            raise KeyError("版本不存在")
        # 写回对应 .md 文件 —— 这一步让热加载即时生效
        path = os.path.join(self.thinking_dir, f"{v.md_name}.md")
        os.makedirs(self.thinking_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(v.content)
        # 旧 live 归档
        old_live = self._live.get(v.md_name)
        if old_live and old_live in self._versions:
            self._versions[old_live].status = "archived"
        v.status = "live"
        self._live[v.md_name] = version_id
        self._log("set_live", md_name=v.md_name, version_id=version_id,
                  from_version=old_live, by=by)
        self._save()
        return v.public()

    def rollback(self, md_name: str, version_id: str, by: str = "admin") -> Dict[str, Any]:
        """回滚 = 把某个历史版本重新设为上线（写回文件）。"""
        v = self._versions.get(version_id)
        if not v or v.md_name != md_name:
            raise KeyError("版本不存在或不属于该 MD")
        result = self.set_live(version_id, by=by)
        self._log("rollback", md_name=md_name, version_id=version_id, by=by)
        self._save()
        return result

    # ---------- 查询 ----------
    def list_versions(self, md_name: str) -> List[Dict[str, Any]]:
        vs = [v for v in self._versions.values() if v.md_name == md_name]
        vs.sort(key=lambda x: x.version, reverse=True)
        live_id = self._live.get(md_name)
        out = []
        for v in vs:
            d = v.public()
            d["is_live"] = (v.id == live_id)
            out.append(d)
        return out

    def list_md_names(self) -> List[str]:
        return sorted({v.md_name for v in self._versions.values()})

    def get_live(self, md_name: str) -> Optional[Dict[str, Any]]:
        vid = self._live.get(md_name)
        return self._versions[vid].public() if vid and vid in self._versions else None

    def get_version(self, version_id: str) -> Optional[Dict[str, Any]]:
        v = self._versions.get(version_id)
        return v.public() if v else None

    def get_content(self, version_id: str) -> Optional[str]:
        v = self._versions.get(version_id)
        return v.content if v else None

    # ---------- diff ----------
    def diff(self, version_a: str, version_b: str) -> Dict[str, Any]:
        va, vb = self._versions.get(version_a), self._versions.get(version_b)
        if not va or not vb:
            raise KeyError("版本不存在")
        diff_lines = list(difflib.unified_diff(
            va.content.splitlines(), vb.content.splitlines(),
            fromfile=f"{va.md_name} v{va.version}", tofile=f"{vb.md_name} v{vb.version}",
            lineterm="",
        ))
        added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
        return {"diff": "\n".join(diff_lines), "added": added, "removed": removed}

    def audit_log(self, md_name: Optional[str] = None) -> List[Dict[str, Any]]:
        if md_name:
            return [a for a in self._audit if a.get("md_name") == md_name]
        return list(self._audit)
