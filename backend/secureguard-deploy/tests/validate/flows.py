# 端到端流程测试:链式调用,验证"一条龙真能用"(最能抓"半拉子/没完成")。
# 每个 flow = 函数(call)->(ok, msg, steps)。call(method,path,body)->(status,json)。
import time

def flow_kb_lifecycle(call):
    """建库 → 文本入库 → 检索能命中。"""
    steps = []
    marker = f"验证专用文本_{int(time.time())}_风管GB50243"
    st, j = call("POST", "/v1/kb/create", {"name": f"__验证库_{int(time.time())}", "visibility": "private"})
    steps.append(("建库", st))
    if not (200 <= st < 300) or not isinstance(j, dict) or not j.get("id"):
        return (False, f"建库失败(HTTP {st})", steps)
    kb_id = j["id"]
    st, j = call("POST", f"/v1/kb/{kb_id}/ingest", {"text": marker})
    steps.append(("入库", st))
    if not (200 <= st < 300):
        return (False, f"入库失败(HTTP {st})", steps)
    time.sleep(0.5)
    st, j = call("POST", "/v1/kb/search", {"query": "风管 GB50243", "k": 5})
    steps.append(("检索", st))
    if not (200 <= st < 300):
        return (False, f"检索失败(HTTP {st})", steps)
    results = (j or {}).get("results", []) if isinstance(j, dict) else []
    hit = any(marker in (r.get("content", "") or "") for r in results)
    return (hit, "检索命中刚入库文本" if hit else "入库了但检索不到(检索链路未打通)", steps)


def flow_agent_create(call):
    """建智能体 → 出现在列表。"""
    steps = []
    name = f"__验证智能体_{int(time.time())}"
    st, j = call("POST", "/v1/admin/agents", {"name": name, "visibility": "private", "description": "验证用"})
    steps.append(("建智能体", st))
    if st == 404:
        st, j = call("POST", "/v1/agents", {"name": name, "visibility": "private"})
        steps.append(("建智能体(备用路径)", st))
    if not (200 <= st < 300):
        return (False, f"建智能体失败(HTTP {st})", steps)
    st, j = call("GET", "/v1/agents", None)
    steps.append(("列表", st))
    found = isinstance(j, list) and any((a.get("name") == name) for a in j)
    return (found, "新建智能体出现在列表" if found else "建了但列表里没有(未真正持久化)", steps)


FLOWS = [
    ("知识库一条龙(建库→入库→检索)", flow_kb_lifecycle),
    ("智能体一条龙(建→列表)", flow_agent_create),
]
