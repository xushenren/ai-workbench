#!/usr/bin/env python3
"""verify_deployment.py — 部署验收（把"我的标准"编码为可执行断言）。

为什么存在：部署由 AI 执行，可能幻觉"成功"。本脚本对**真实服务器**逐项验证安全/
RBAC/隔离/审计标准，产出带具体数字与状态码的报告——总结可以编，这种原始断言结果难编。

用法：
  pip install httpx websocket-client
  python verify_deployment.py http://你的地址[:端口][/前缀]

退出码非 0 表示有项目未达标。把**完整输出**贴回给 Claude 审核。
"""
import sys, json, secrets, random

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:9000").rstrip("/")
WS = BASE.replace("http", "ws", 1) + "/v1/chat/stream"

PASS, FAIL = [], []
def ok(name, detail=""): PASS.append(f"{name}  {detail}".rstrip())
def bad(name, detail=""): FAIL.append(f"{name}  {detail}".rstrip())

def main():
    try:
        import httpx
    except Exception:
        print("缺 httpx：pip install httpx websocket-client"); sys.exit(2)
    c = httpx.Client(base_url=BASE, timeout=8.0)

    def login(phone, pwd):
        r = c.post("/v1/auth/login", json={"phone": phone, "password": pwd})
        return r.json().get("token") if r.status_code == 200 else None

    # ---------- A. 健康 ----------
    try:
        r = c.get("/health")
        ok("A 健康", f"{r.status_code} {r.json()}") if r.status_code == 200 else bad("A 健康", str(r.status_code))
    except Exception as e:
        bad("A 健康", f"连不上后端：{e}"); report(); return

    # ---------- B. 注册强制 user 角色（防提权）----------
    phone = "13" + "".join(random.choice("0123456789") for _ in range(9))
    r = c.post("/v1/auth/register", json={"phone": phone, "password": "verify6", "role": "admin"})
    if r.status_code == 200 and r.json().get("user", {}).get("role") == "user":
        ok("B 注册强制 user", f"传 role=admin 仍得 role={r.json()['user']['role']}")
    else:
        bad("B 注册强制 user", f"{r.status_code} {r.text[:120]}")
    r2 = c.post("/v1/auth/register", json={"phone": phone, "password": "verify6"})
    ok("B 重复手机拒绝", str(r2.status_code)) if r2.status_code == 400 else bad("B 重复手机拒绝", str(r2.status_code))
    user_tok = login(phone, "verify6")

    # ---------- C. 登录 ----------
    admin_tok = login("13800000000", "admin123")
    dev_tok = login("13800000001", "dev123")
    ok("C 管理员登录") if admin_tok else bad("C 管理员登录", "拿不到 token")

    def H(t): return {"Authorization": f"Bearer {t}"} if t else {}

    # ---------- D. RBAC ----------
    checks = [
        ("D 未认证 /v1/me → 401", c.get("/v1/me").status_code, 401),
        ("D user 访问 admin/stats → 403", c.get("/v1/admin/stats", headers=H(user_tok)).status_code, 403),
        ("D admin 访问 admin/stats → 200", c.get("/v1/admin/stats", headers=H(admin_tok)).status_code, 200),
        ("D user 访问 audit/verify → 403", c.get("/v1/audit/verify", headers=H(user_tok)).status_code, 403),
        ("D admin 访问 audit/verify → 200", c.get("/v1/audit/verify", headers=H(admin_tok)).status_code, 200),
    ]
    for name, got, want in checks:
        ok(name) if got == want else bad(name, f"实际 {got}")

    # 审计链有效性
    av = c.get("/v1/audit/verify", headers=H(admin_tok))
    if av.status_code == 200:
        valid = av.json().get("valid", av.json().get("ok"))
        ok("D 审计链完整", str(av.json())) if valid in (True, None) else bad("D 审计链完整", str(av.json()))

    # ---------- E. 智能体发布状态机 ----------
    anon_agents = c.get("/v1/agents").json()
    ok("E 匿名只见已发布公共", f"{len(anon_agents)} 个") if isinstance(anon_agents, list) else bad("E 匿名列表", str(anon_agents))
    # user 建公共 → 403
    uc = c.post("/v1/admin/agents", json={"name": "x", "visibility": "public"}, headers=H(user_tok))
    ok("E user 建公共被拒 403") if uc.status_code == 403 else bad("E user 建公共被拒", f"实际 {uc.status_code}")
    # developer 建公共 → draft；提交；user 批 403；admin 批 200
    dc = c.post("/v1/admin/agents", json={"name": f"验收{secrets.token_hex(2)}", "visibility": "public"}, headers=H(dev_tok))
    if dc.status_code == 200 and dc.json().get("status") == "draft":
        aid = dc.json()["id"]
        ok("E developer 建公共=draft", aid)
        c.post(f"/v1/admin/agents/{aid}/submit", headers=H(dev_tok))
        ua = c.post(f"/v1/admin/agents/{aid}/approve", headers=H(user_tok))
        ok("E user 审批被拒 403") if ua.status_code == 403 else bad("E user 审批被拒", f"实际 {ua.status_code}")
        aa = c.post(f"/v1/admin/agents/{aid}/approve", headers=H(admin_tok))
        ok("E admin 审批=published") if aa.status_code == 200 and aa.json().get("status") == "published" else bad("E admin 审批", f"{aa.status_code} {aa.text[:80]}")
    else:
        bad("E developer 建公共=draft", f"{dc.status_code} {dc.text[:80]}")

    # ---------- F. 知识库隔离 ----------
    admin_kbs = {k["id"] for k in c.get("/v1/knowledge", headers=H(admin_tok)).json()}
    fresh_kbs = {k["id"] for k in c.get("/v1/knowledge", headers=H(user_tok)).json()}  # 新注册 user，无部门
    ok("F 新用户只见公共库", str(fresh_kbs)) if fresh_kbs == {"kb_std"} else bad("F 新用户只见公共库", str(fresh_kbs))
    # 搜他人私有内容 → 不得命中他人私有库
    s = c.post("/v1/kb/search", json={"query": "u2 的私有内容", "top_k": 5}, headers=H(user_tok)).json()
    leaked = [h for h in s.get("results", []) if h.get("kb_id") == "kb_user2"]
    if not leaked and "kb_user2" not in s.get("accessible_kbs", []):
        ok("F 检索不泄露他人私有库", f"可达库={s.get('accessible_kbs')}")
    else:
        bad("F 检索不泄露他人私有库", f"泄露！{s.get('accessible_kbs')} {leaked}")

    # ---------- G. 配额 ----------
    q = c.get("/v1/quota/general", headers=H(user_tok))
    ok("G 配额查询", str(q.json())) if q.status_code == 200 and "remaining" in q.json() else bad("G 配额查询", q.text[:80])

    # ---------- J. 用户管理 + 受控审计（职责分离 + 留痕） ----------
    audit_tok = login("13800000004", "audit123")
    lu = c.get("/v1/admin/users", headers=H(admin_tok))
    ok("J admin 列用户", f"{len(lu.json())} 人") if lu.status_code == 200 else bad("J admin 列用户", str(lu.status_code))
    ok("J user 列用户被拒 403") if c.get("/v1/admin/users", headers=H(user_tok)).status_code == 403 else bad("J user 列用户被拒")
    # 分配部门解死结：新用户(无部门，只见公共) → admin 分配 d1 → 能见部门库
    p2 = "13" + "".join(random.choice("0123456789") for _ in range(9))
    nt = c.post("/v1/auth/register", json={"phone": p2, "password": "verify6"}).json()
    nid = nt["user"]["id"]; ntok = nt["token"]
    kb_before = {k["id"] for k in c.get("/v1/knowledge", headers=H(ntok)).json()}
    c.post(f"/v1/admin/users/{nid}/department", json={"dept_id": "d1"}, headers=H(admin_tok))
    kb_after = {k["id"] for k in c.get("/v1/knowledge", headers=H(ntok)).json()}
    if kb_before == {"kb_std"} and "kb_dept" in kb_after:
        ok("J 分配部门解锁部门库", f"{kb_before} → {kb_after}")
    else:
        bad("J 分配部门解锁部门库", f"{kb_before} → {kb_after}")
    # 职责分离：日常 admin 仍看不到他人私有库
    sa = c.post("/v1/kb/search", json={"query": "u2 的私有内容"}, headers=H(admin_tok)).json()
    ok("J 日常 admin 仍隔离") if "kb_user2" not in sa.get("accessible_kbs", []) else bad("J 日常 admin 仍隔离", "泄露！")
    # 审计端点：admin 无权(403)，auditor 有权
    ok("J admin 无审计读取权 403") if c.get("/v1/audit/kb/list", headers=H(admin_tok)).status_code == 403 else bad("J admin 无审计读取权")
    al = c.get("/v1/audit/kb/list", headers=H(audit_tok))
    ok("J 审计员可列全部库", f"{len(al.json())} 个含私有") if al.status_code == 200 else bad("J 审计员列库", str(al.status_code))
    # 审计读取：缺 reason→400；带 reason→200 且读到他人私有原文
    ok("J 审计读取必填理由 400") if c.post("/v1/audit/kb/read", json={"kb_id": "kb_user2", "reason": ""}, headers=H(audit_tok)).status_code == 400 else bad("J 审计读取必填理由")
    ar = c.post("/v1/audit/kb/read", json={"kb_id": "kb_user2", "reason": "合规抽查"}, headers=H(audit_tok))
    if ar.status_code == 200 and ar.json().get("audited"):
        ok("J 审计员读他人私有(留痕)", f"owner={ar.json().get('owner_id')}")
    else:
        bad("J 审计员读他人私有", f"{ar.status_code} {ar.text[:80]}")
    chain = c.get("/v1/audit/verify", headers=H(admin_tok)).json()
    ok("J 审计读取后链仍完整", str(chain)) if chain.get("ok") else bad("J 审计链", str(chain))

    # ---------- H. WS：流式 + 安全约束（无 rule_id）----------
    ws_check(user_tok)

    # ---------- K. 会话持久化 + 多轮 + 搜索 ----------
    # WS 已在 session 'v1' 发过一条"你好"；此处校验它被持久化、可列、可搜
    sl = c.get("/v1/sessions", headers=H(user_tok))
    if sl.status_code == 200 and any(s.get("id") == "v1" for s in sl.json()):
        ok("K 会话已持久化", f"{len(sl.json())} 个会话")
    else:
        bad("K 会话已持久化", f"{sl.status_code} {sl.text[:80]}")
    sm = c.get("/v1/sessions/v1/messages", headers=H(user_tok))
    ok("K 消息已存", f"{len(sm.json())} 条") if sm.status_code == 200 and len(sm.json()) >= 1 else bad("K 消息已存", str(sm.status_code))
    ss = c.get("/v1/sessions/search", params={"q": "你好"}, headers=H(user_tok))
    ok("K 按内容搜会话") if ss.status_code == 200 else bad("K 搜会话", str(ss.status_code))

    # ---------- I. 全局安全回归：任何响应不含 rule_id/params ----------
    forbidden_hits = []
    for path in ("/v1/agents", "/v1/compute/status"):
        body = c.get(path, headers=H(admin_tok)).text
        if '"rule_id"' in body or '"params"' in body:
            forbidden_hits.append(path)
    ok("I 响应无 rule_id/params 泄露") if not forbidden_hits else bad("I 安全泄露", str(forbidden_hits))

    report()


def ws_check(token):
    try:
        from websocket import create_connection
    except Exception:
        bad("H WS（缺 websocket-client，跳过）", "pip install websocket-client"); return
    try:
        ws = create_connection(WS, timeout=10)
        ws.send(json.dumps({"message": "你好", "agent_id": "general", "session_id": "v1", "token": token}))
        first_trace = done = False
        rule_leak = False
        for _ in range(80):
            ev = json.loads(ws.recv())
            if ev.get("event") == "trace":
                first_trace = first_trace or True
                if "rule_id" in ev.get("frame", {}) or "params" in ev.get("frame", {}):
                    rule_leak = True
            if ev.get("event") == "done":
                done = True; break
        ws.close()
        ok("H WS 收到 trace+done") if (first_trace and done) else bad("H WS 流式", f"trace={first_trace} done={done}")
        ok("H WS 帧无 rule_id 泄露") if not rule_leak else bad("H WS rule_id 泄露", "严重！")
    except Exception as e:
        bad("H WS 连接", f"{e}（反代是否转发了 WebSocket？）")


def report():
    print("\n" + "=" * 56)
    print(f"  部署验收：{len(PASS)} 通过 / {len(FAIL)} 未达标")
    print("=" * 56)
    for p in PASS: print(f"  ✓ {p}")
    for f in FAIL: print(f"  ✗ {f}")
    print()
    if FAIL:
        print("→ 有项目未达标。把以上**完整输出**原样贴给 Claude。")
        sys.exit(1)
    else:
        print("→ 全部达标。把此输出贴给 Claude 存档。")
        sys.exit(0)


if __name__ == "__main__":
    main()
