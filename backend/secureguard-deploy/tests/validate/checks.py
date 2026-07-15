# 功能验证用例:每条 = (名称, 方法, 路径, 请求体, 判定函数)。judge(status, json)->(ok, msg)。
# 真调接口、看真实返回,抓"没实现/坏了/装一半"。只读或可回滚的操作优先;写操作用测试前缀数据。

def ok2xx(s, j): return (200 <= s < 300, f"HTTP {s}")

def has_keys(*ks):
    def f(s, j):
        if not (200 <= s < 300): return (False, f"HTTP {s}")
        if not isinstance(j, (dict, list)): return (False, "返回非JSON")
        d = j[0] if isinstance(j, list) and j else j
        miss = [k for k in ks if isinstance(d, dict) and k not in d]
        return (not miss, "缺字段:" + ",".join(miss) if miss else "ok")
    return f

def is_list(s, j): return (200 <= s < 300 and isinstance(j, list), "应返回列表" if not isinstance(j, list) else "ok")

# 每条:name, method, path, body(dict或None), judge, [need_admin]
CHECKS = [
  # --- 基础/健康 ---
  ("健康检查", "GET", "/health", None, ok2xx, False),
  ("当前用户", "GET", "/v1/me", None, ok2xx, False),

  # --- 知识库 ---
  ("知识库列表", "GET", "/v1/knowledge", None, ok2xx, False),
  ("建知识库", "POST", "/v1/kb/create", {"name":"__验证库__","visibility":"private"}, has_keys("id"), False),
  ("知识库检索", "POST", "/v1/kb/search", {"query":"测试","k":3}, has_keys("results"), False),
  ("入库配置读取", "GET", "/v1/kb/ingest-config", None, ok2xx, True),
  ("解析器映射表", "GET", "/v1/kb/parsers", None, is_list, True),
  ("字段类型建议", "POST", "/v1/kb/fields/suggest", {"name":"是否防火"}, has_keys("suggested_type"), False),

  # --- 智能体 ---
  ("智能体列表", "GET", "/v1/agents", None, ok2xx, False),

  # --- 模型管理 ---
  ("模型列表", "GET", "/v1/models/all", None, is_list, True),
  ("模型厂商预设", "GET", "/v1/models/providers", None, ok2xx, True),

  # --- 白标 ---
  ("白标读取", "GET", "/v1/branding", None, has_keys("platform_name"), False),

  # --- 用户/组织 ---
  ("用户导入模板", "GET", "/v1/users/import/template", None, ok2xx, True),
  ("组织树", "GET", "/v1/org/tree", None, ok2xx, True),
  ("组织人员", "GET", "/v1/org/users", None, is_list, True),
  ("组织岗位", "GET", "/v1/org/roles", None, is_list, True),
  ("权限位清单", "GET", "/v1/org/perms", None, is_list, True),
  ("组织导入模板", "GET", "/v1/org/import/template", None, ok2xx, True),

  # --- 存储/搬迁 ---
  ("整站导出", "POST", "/v1/admin/site/export", None, ok2xx, True),

  # --- Coze 融入 ---
  ("Coze SSO", "POST", "/v1/coze/sso", None, ok2xx, False),
]
