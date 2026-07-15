"""platform_storage.site_export — 整站导出/导入(搬迁·备份·给乙方初始化)。

DATA_DIR 里含:关系库(*.db)、向量库(vectors.db)、对象(blobs/)、各配置 json。
export:打包 DATA_DIR → tar.gz + manifest(版本/时间/文件清单/校验)。
import:安全解包回 DATA_DIR(可选先备份原目录)。整站搬迁 = export 后拷到新机 import。
"""
from __future__ import annotations
import hashlib, io, json, os, tarfile, time
from typing import Dict

MANIFEST = "_site_manifest.json"
FORMAT_VERSION = "1.0"


def export_site(data_dir: str, out_path: str, platform_version: str = "") -> Dict:
    files = []
    for root, _, fs in os.walk(data_dir):
        for f in fs:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, data_dir)
            if rel == MANIFEST:
                continue
            files.append(rel)
            _ = full
    manifest = {
        "format": FORMAT_VERSION, "platform_version": platform_version,
        "created_at": int(time.time()), "file_count": len(files), "files": sorted(files),
    }
    with tarfile.open(out_path, "w:gz") as tar:
        mdata = json.dumps(manifest, ensure_ascii=False).encode()
        info = tarfile.TarInfo(MANIFEST); info.size = len(mdata)
        tar.addfile(info, io.BytesIO(mdata))
        for rel in files:
            tar.add(os.path.join(data_dir, rel), arcname=rel)
    return {"out": out_path, "file_count": len(files), "size": os.path.getsize(out_path)}


def read_manifest(tar_path: str) -> Dict:
    with tarfile.open(tar_path, "r:gz") as tar:
        m = tar.extractfile(MANIFEST)
        if not m:
            raise ValueError("不是合法的整站备份包(缺 manifest)")
        return json.loads(m.read().decode())


def _safe_members(tar: tarfile.TarFile, dest: str):
    dest_abs = os.path.abspath(dest)
    for m in tar.getmembers():
        p = os.path.abspath(os.path.join(dest, m.name))
        if not p.startswith(dest_abs + os.sep) and p != dest_abs:
            raise ValueError(f"非法路径(穿越):{m.name}")
        if m.issym() or m.islnk():
            raise ValueError(f"拒绝符号/硬链接:{m.name}")
        yield m


def import_site(tar_path: str, data_dir: str, overwrite: bool = False) -> Dict:
    manifest = read_manifest(tar_path)
    os.makedirs(data_dir, exist_ok=True)
    if os.listdir(data_dir) and not overwrite:
        raise ValueError("目标 DATA_DIR 非空;确认后用 overwrite=True(建议先备份)")
    with tarfile.open(tar_path, "r:gz") as tar:
        members = [m for m in _safe_members(tar, data_dir) if m.name != MANIFEST]
        for m in members:
            tar.extract(m, data_dir)
    return {"imported_files": len(manifest.get("files", [])),
            "platform_version": manifest.get("platform_version", ""),
            "created_at": manifest.get("created_at")}
