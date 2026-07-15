"""tests/test_audit_chain.py — D5 审计哈希链单测。"""
import sys, os, json, tempfile, shutil
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from secureguard.l4_audit import AuditLogger, AuditEntry, GENESIS_HASH
from secureguard.audit_rotation import RotatingAuditLogger


def test_normal_chain_verifies():
    a = AuditLogger()
    for i in range(5):
        a.log_stage(stage="L1", decision="PASS", reason=f"step{i}")
    res = a.verify_chain()
    assert res["ok"] and res["length"] == 5
    # 首条 prev_hash 为 genesis
    assert a.entries[0].prev_hash == GENESIS_HASH


def test_each_entry_links_to_previous():
    a = AuditLogger()
    e1 = a.log_stage(stage="L0", decision="PASS")
    e2 = a.log_stage(stage="L1", decision="PASS")
    assert e2.prev_hash == e1.entry_hash  # 链接正确


def test_tamper_detected():
    a = AuditLogger()
    for i in range(5):
        a.log_stage(stage="L1", decision="PASS", reason=f"step{i}")
    # 篡改中间一条的内容（reason），但不重算哈希 → 必须被检出
    a.entries[2].reason = "TAMPERED"
    res = a.verify_chain()
    assert res["ok"] is False and res["broken_at"] == 2


def test_relink_tamper_also_detected():
    # 即便攻击者重算了被改条目的 entry_hash，后一条的 prev_hash 仍对不上 → 断链
    a = AuditLogger()
    for i in range(4):
        a.log_stage(stage="L1", decision="PASS", reason=f"s{i}")
    a.entries[1].reason = "EVIL"
    a.entries[1].entry_hash = a.entries[1].compute_hash()  # 重算自身
    res = a.verify_chain()
    assert res["ok"] is False and res["broken_at"] == 2  # 下一条链接断裂


def test_cross_file_chain_after_rotation():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "audit.jsonl")
    # backup_count 调大以保留全链（含 genesis 分卷），便于从头校验
    log = RotatingAuditLogger(path, max_bytes=400, backup_count=50, retention_days=None)
    for i in range(40):
        log.log(AuditEntry(stage="L4", decision="PASS", reason="x" * 15))
    assert os.path.exists(path + ".1")  # 确实轮转了
    # 按时间顺序：最旧分卷(最大序号) → … → 当前文件
    import glob
    rotated = sorted(glob.glob(path + ".*"),
                     key=lambda p: int(p.rsplit(".", 1)[1]), reverse=True)
    ordered = rotated + [path]
    res = AuditLogger.verify_files(ordered)
    assert res["ok"], res
    shutil.rmtree(d)


def test_pruned_chain_verifies_survivor_segment():
    # 保留策略裁掉最早分卷后，幸存中段仍应内部连续（require_genesis=False）
    d = tempfile.mkdtemp()
    path = os.path.join(d, "audit.jsonl")
    log = RotatingAuditLogger(path, max_bytes=400, backup_count=3, retention_days=None)
    for i in range(40):
        log.log(AuditEntry(stage="L4", decision="PASS", reason="y" * 15))
    import glob
    rotated = sorted(glob.glob(path + ".*"),
                     key=lambda p: int(p.rsplit(".", 1)[1]), reverse=True)
    res = AuditLogger.verify_files(rotated + [path], require_genesis=False)
    assert res["ok"], res
    shutil.rmtree(d)


def test_genesis_restored_across_logger_restart():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "audit.jsonl")
    a1 = AuditLogger(path=path)
    a1.log_stage(stage="L0", decision="PASS")
    last = a1.entries[-1].entry_hash
    # 新 logger 实例打开同一文件，应从末行恢复链头
    a2 = AuditLogger(path=path)
    e = a2.log_stage(stage="L1", decision="PASS")
    assert e.prev_hash == last  # 跨重启链连续
    res = AuditLogger.verify_files([path])
    assert res["ok"]
    shutil.rmtree(d)
