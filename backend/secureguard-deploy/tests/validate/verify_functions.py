#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功能自动验证(冒烟测试)—— 龙虾一键跑,真调接口看真实返回,抓"没实现/坏了/装一半"。
用法:
    python3 verify_functions.py --base http://127.0.0.1:9002 --token <管理员token>
  或用账号密码自动登录取 token:
    python3 verify_functions.py --base http://127.0.0.1:9002 --phone 13800000000 --password admin123
输出:每个功能 [通过/失败/未实现] + 原因;末尾汇总。贴回来我据此定位。
仅用 stdlib(urllib),无需装任何东西。
"""
import argparse, json, sys, urllib.request, urllib.error

from checks import CHECKS

G, R, Y, GRY, RST = "\033[92m", "\033[91m", "\033[93m", "\033[90m", "\033[0m"
def col(t, c): return f"{c}{t}{RST}" if sys.stdout.isatty() else t


def http(method, url, token=None, body=None, timeout=20):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try: j = json.loads(raw)
            except Exception: j = raw[:200].decode("utf-8", "ignore")
            return r.status, j
    except urllib.error.HTTPError as e:
        raw = e.read()
        try: j = json.loads(raw)
        except Exception: j = raw[:200].decode("utf-8", "ignore")
        return e.code, j
    except Exception as e:
        return 0, str(e)


def login(base, phone, password):
    for path in ("/v1/auth/login",):
        st, j = http("POST", base + path, body={"phone": phone, "password": password})
        if 200 <= st < 300 and isinstance(j, dict):
            tok = j.get("token") or j.get("access_token") or (j.get("data") or {}).get("token")
            if tok: return tok
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="后端地址,如 http://127.0.0.1:9002")
    ap.add_argument("--token", default=None)
    ap.add_argument("--phone", default=None)
    ap.add_argument("--password", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--flow", action="store_true", help="额外跑端到端流程(会建测试数据)")
    a = ap.parse_args()
    base = a.base.rstrip("/")

    token = a.token
    if not token and a.phone and a.password:
        token = login(base, a.phone, a.password)
        if not token:
            print(col("登录失败:拿不到 token,请改用 --token 直接传", R)); sys.exit(2)

    results = []
    for name, method, path, body, judge, need_admin in CHECKS:
        st, j = http(method, base + path, token=token, body=body)
        if st == 0:
            status, msg = "ERROR", f"连不上/异常:{j}"
        elif st == 404:
            status, msg = "未实现", "404 端点不存在(功能可能没部署/没实现)"
        elif st == 401 and need_admin and not token:
            status, msg = "跳过", "需要管理员 token(未提供)"
        else:
            ok, m = judge(st, j)
            status, msg = ("通过" if ok else "失败"), m
        results.append({"name": name, "path": path, "http": st, "status": status, "msg": msg})

    if a.json:
        print(json.dumps(results, ensure_ascii=False, indent=2)); return

    tag = {"通过": col("✓ 通过", G), "失败": col("✗ 失败", R),
           "未实现": col("✗ 未实现", R), "ERROR": col("✗ 异常", R), "跳过": col("- 跳过", GRY)}
    for r in results:
        print(f"[{tag[r['status']]}] {r['name']:<16} {col(r['path'],GRY)}")
        if r["status"] not in ("通过", "跳过"):
            print(f"        HTTP {r['http']} · {col(r['msg'], Y)}")
    if a.flow:
        from flows import FLOWS
        print("\n=== 端到端流程 ===")
        def call(method, path, body=None):
            return http(method, base + path, token=token, body=body)
        for fname, ffn in FLOWS:
            try:
                ok, msg, steps = ffn(call)
            except Exception as e:
                ok, msg, steps = False, f"异常:{e}", []
            stag = col("✓ 通过", G) if ok else col("✗ 失败", R)
            chain = " → ".join(f"{n}({s})" for n, s in steps)
            print(f"[{stag}] {fname}")
            print(f"        {col(chain, GRY)}")
            if not ok: print(f"        {col(msg, Y)}")

    n_ok = sum(1 for r in results if r["status"] == "通过")
    n_bad = sum(1 for r in results if r["status"] in ("失败", "未实现", "ERROR"))
    n_skip = sum(1 for r in results if r["status"] == "跳过")
    print(f"\n汇总: {col(str(n_ok)+' 通过', G)} / {col(str(n_bad)+' 有问题', R if n_bad else GRY)} / {n_skip} 跳过  (共 {len(results)})")
    print("把整段贴回,失败/未实现的我逐个定位补。")


if __name__ == "__main__":
    main()
