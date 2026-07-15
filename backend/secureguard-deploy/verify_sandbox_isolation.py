#!/usr/bin/env python3
"""沙箱隔离实测 —— 必须在你的服务器上跑（需 Docker）。

目的：证明 Docker 沙箱**真的隔离住了**，而不只是"代码写了隔离参数"。
本脚本喂给沙箱 5 段恶意代码，预期它们全部被挡。把完整输出贴回给 Claude 审。

用法（在 secureguard 目录、服务器上）：
    # 1) 先确保镜像在
    docker pull python:3.12-slim
    # 2) 用 docker 后端跑本脚本
    SANDBOX_BACKEND=docker SANDBOX_IMAGE=python:3.12-slim python3 verify_sandbox_isolation.py

判定标准（每项必须达标，否则隔离不合格、勿对不可信代码开放）：
  [1] 禁网：urlopen 必须失败（--network=none 生效）
  [2] 读敏感文件：读 /etc/shadow 必须失败或为空（只读+非root）
  [3] fork 炸弹：必须被 pids-limit 挡住，不能拖垮主机
  [4] 写根文件系统：必须失败（--read-only 生效）
  [5] 后端确认：返回 backend=='docker'（不是静默退回 subprocess）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.sandbox_executor import build_executor

# 强制要求 docker 后端，避免误用子进程版自欺
if os.environ.get("SANDBOX_BACKEND") != "docker":
    print("⚠️  请用 SANDBOX_BACKEND=docker 运行，否则测的不是真隔离。")
    print("   SANDBOX_BACKEND=docker SANDBOX_IMAGE=python:3.12-slim python3 verify_sandbox_isolation.py")
    sys.exit(1)

ex = build_executor()

TESTS = [
    ("1) 禁网测试（应失败）", """
import urllib.request
try:
    urllib.request.urlopen("http://example.com", timeout=5)
    print("NETWORK_REACHABLE")      # 出现这个 = 隔离失败
except Exception as e:
    print("NETWORK_BLOCKED:", type(e).__name__)
"""),
    ("2) 读 /etc/shadow（应失败/为空）", """
try:
    with open("/etc/shadow") as f:
        data = f.read()
    print("SHADOW_READ_LEN:", len(data))   # 非0 = 读到了，隔离失败
except Exception as e:
    print("SHADOW_BLOCKED:", type(e).__name__)
"""),
    ("3) fork 炸弹（应被 pids-limit 挡）", """
import os
count = 0
try:
    for _ in range(10000):
        os.fork()
        count += 1
except Exception as e:
    print("FORK_BLOCKED_AFTER:", count, type(e).__name__)
"""),
    ("4) 写根文件系统（应失败）", """
try:
    with open("/evil.txt", "w") as f:
        f.write("pwned")
    print("ROOT_WRITE_OK")          # 出现 = 只读没生效，隔离失败
except Exception as e:
    print("ROOT_WRITE_BLOCKED:", type(e).__name__)
"""),
    ("5) 正常代码（应成功，确认沙箱可用）", """
print("HELLO_FROM_SANDBOX", 2 + 2)
"""),
]

print("=" * 60)
print("沙箱隔离实测 —— 把以下完整输出贴回给 Claude")
print("=" * 60)

backend_seen = None
for title, code in TESTS:
    print("\n" + title)
    r = ex.execute(code)
    backend_seen = r.get("backend")
    print("  backend :", r.get("backend"))
    print("  exit    :", r.get("exit_code"))
    print("  timed_out:", r.get("timed_out"))
    print("  stdout  :", repr((r.get("stdout") or "").strip()[:300]))
    print("  stderr  :", repr((r.get("stderr") or "").strip()[:200]))
    print("  error   :", r.get("error"))

print("\n" + "=" * 60)
print("自动判定（仅供参考，以实际输出为准）：")
print(f"  后端是否为 docker: {'✅' if backend_seen == 'docker' else '❌ 不是 docker！测的不是真隔离'}")
print("  逐项请人工核对上方 stdout：")
print("    [1] 应出现 NETWORK_BLOCKED，不能有 NETWORK_REACHABLE")
print("    [2] 应出现 SHADOW_BLOCKED 或 SHADOW_READ_LEN: 0")
print("    [3] 应出现 FORK_BLOCKED_AFTER（数字应远小于 10000）")
print("    [4] 应出现 ROOT_WRITE_BLOCKED，不能有 ROOT_WRITE_OK")
print("    [5] 应出现 HELLO_FROM_SANDBOX 4（确认正常代码能跑）")
print("=" * 60)
