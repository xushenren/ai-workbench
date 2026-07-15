# 上安 v2.0 · Kun / Kimi / Artifacts 集成落地包

> 目标：把 **Kun（体验 + 省Token方法论）**、**Kimi（多专家系统方法论）**、**Artifacts** 三者的优点
> 吸收进上安 `:9000` 中台。全程中间件模式，不改 OpenClaw 源码，不动 Kun 代码，技术栈不变（Python/FastAPI/React/Vite，单机）。

---

## 0. 先把那个「或者」定下来

你问的是"集成进我的平台" **还是** "改写 Kun 来集成我的平台"。
你 spec 第二节「核心架构（已决策，不讨论）」其实已经选了——**Kun 当桌面外壳不动**，靠
`Provider base_url + MCP` 接上安；上安只吸收 Kun 的**方法论**（省Token），不接管它的壳。
所以本包按这个既定方向落地，不重开架构讨论（你 spec 第七条也禁止了）。
`置信度: 高 — 直接遵循你已定稿的决策。`

三样东西的落点，一句话各自归位：

| 吸收对象 | 取它什么 | 落在哪 | 对应文件 | 真实度 |
|---|---|---|---|---|
| **Kun** | 6层省Token方法论 | 消息管道中间件 | `token_saver.py` | 算法完整；嵌入/向量库/摘要器是注入点 |
| **Kun** | 桌面体验 | 不吸收，外壳直接用 | Provider+MCP 配置（§3） | 配置级 |
| **Kimi** | 多专家三级召回 + 难度分级 | OpenClaw Agent 之上的路由层 | `expert_router.py` | 算法完整；专家库读你的 Skill 文件 |
| **Artifacts** | 结构化成果产出+渲染 | 后端抽取 + /app 面板 | `artifacts.py` + `ArtifactPanel.jsx` | 完整；Kun 端降级为纯文本 |
| 三者汇流 | 统一编排 | 扩展现有 `/v1/openai/chat/completions` | `pipeline.py` | 完整骨架，可跑 |

---

## 1. 一个请求怎么穿过三层

```
Kun / OpenClaw 发来 OpenAI 兼容请求
        │  POST /v1/openai/chat/completions   (pipeline.py，即 spec 任务1 的"扩展")
        ▼
  ┌─ ExpertRouter.route()  ── Kimi ──  L1规则<1ms → L2语义~10ms → L3确认~300ms
  │      └─ 注入命中 Skill 的 System Prompt（含 Artifacts 产出协议）
  │      └─ 难度分级 → 选模型（easy:flash / medium:pro / hard:MechDistill 7B）
  │
  ├─ SemanticCache.lookup() ── Kun L6 ── 同路由且相似>0.95 → 直接返回，不调模型
  │
  ├─ TokenSaver.pre()      ── Kun L3/L5/L1/L2 ── 结果压缩→上下文压缩→前缀固化→工具收起
  │
  ├─ infer()               ── 调上游裸模型（MODEL_UPSTREAM）
  │
  ├─ extract_artifacts()   ── Artifacts ── 抽 ```artifact``` 围栏 → x_shangan_artifacts
  │
  └─ SemanticCache.store() + 观测元数据(x_shangan_meta)
        │
        ▼
  OpenAI 兼容响应（Kun 只读 content；/app 读 x_shangan_artifacts 渲染卡片）
```

为什么**路由在省Token之前**：路由会重写 system 段（注入 Skill），而 L1 前缀固化要对最终 system 段算
SHA256 才能让上游 prefix-cache 稳定命中。顺序反了会让缓存永远 miss。
`置信度: 高 — 这是顺序敏感点，已按此实现。`

L4 Storm 抑制不在 `pre()` 里，因为它依赖"模型回了工具调用"这个事件，在 OpenClaw 的 agent loop 里逐轮检查；
`StormSuppressor.check()` 已备好，接 loop 时每次工具调用前调一次即可。
`假设: OpenClaw 的工具调用可在网关侧拦到 (conv_id, tool, args)。若拿不到，L4 退化为按 messages 里重复 tool_call 检测。`

---

## 2. 文件清单

```
shangan_integration/
  pipeline.py        统一编排端点 + 工具按需加载回填端点  ← include_router 这个
  token_saver.py     Kun 6层省Token（L1~L6）
  expert_router.py   Kimi 三级召回 + 难度分级 + Skill注入
  artifacts.py       Artifacts 抽取/产出协议
  mcp_server.py      Kun MCP：shangan-knowledge / shangan-tasks
web/
  ArtifactPanel.jsx  /app Write模式的 Artifact 渲染面板
```

挂载（在你现有 :9000 app 上加两行，旧逻辑不删）：

```python
from shangan_integration.pipeline import api as shangan_api
from shangan_integration.mcp_server import mcp as shangan_mcp
app.include_router(shangan_api)
app.include_router(shangan_mcp)
# 旧的 /v1/openai/chat/completions 改名为裸转发端点，让 MODEL_UPSTREAM 指过去
```

环境变量（单机，无 Docker）：

```bash
export MODEL_UPSTREAM=http://127.0.0.1:8001/v1   # 裸模型服务（避免本端点自调用递归）
export SKILL_BASE=/data/standards_downloads/rag/experts
export MODEL_FLASH=deepseek-v4-flash
export MODEL_PRO=deepseek-v4-pro
export MODEL_EXPERT=mechanical-expert
uvicorn app:app --host 0.0.0.0 --port 9000
```

---

## 3. Kun 对接配置（spec 任务6，零代码）

**Provider**：
```
Base URL: http://115.190.145.150/v1/openai
模型:     mechanical-expert / deepseek-v4-pro / deepseek-v4-flash
```
（注意：模型名照填，平台内部会按难度分级再覆盖选择；填哪个都能用，填 pro 最稳。）

**MCP Server**（Kun 设置里加两个）：
```
shangan-knowledge → http://115.190.145.150/v1/mcp/knowledge
shangan-tasks     → http://115.190.145.150/v1/mcp/tasks
```
拉取 manifest（GET）拿到工具清单，调用走 POST `{name, arguments}`。
`假设: Kun 的 MCP 客户端支持 MCP-over-HTTP。若它只认 stdio/SSE，mcp_server.py 的工具 schema 与 handler 原样可搬到官方 mcp SDK，传输层换掉即可。`

---

## 4. 三处必须由你方回填的真实依赖

代码里都标了注入点，未接通时安全降级（不报错、只是该能力 no-op）：

1. **`build_deps()`（pipeline.py）**：`embed`=bge-m3、`semantic_cache_store`=LanceDB 表、`summarize`=摘要小模型。
   不接 → L6语义缓存/L5上下文压缩/L2语义路由自动跳过，其余照常。
2. **专家库（expert_router.py）**：`SKILL_BASE` 指向你 14 Skill+14 行业+15 交叉的 md 目录。
   建议给每个 md 加 frontmatter `keywords:[...]` 提升 L1 命中；没有则自动抽词兜底。
3. **MCP 检索/任务（mcp_server.py）**：`RAG_SEARCH`、`EVA_TASKS` 两个回调接你现有实现。

---

## 5. 与 spec 任务的对应关系（哪做完了、哪是骨架）

| spec 任务 | 本包覆盖 | 状态 |
|---|---|---|
| 任务1 知识API封装（自动路由+引用） | pipeline.py 编排 + 难度分级选模型 | ✅ 骨架可跑；"自动引用"需 RAG 接入后在 system 注入来源 |
| 任务2 RAG 向量入库 | — | ❌ 本包不含入库脚本（要你的切片真数据），是 §4.1 的注入点 |
| 任务3 专家路由 | expert_router.py 三级召回 + Skill注入 | ✅ 完整 |
| 任务4 省Token 6层 | token_saver.py | ✅ 完整（L1/L2/L3/L5/L6 已接管道；L4 待接 agent loop） |
| 任务5 平台统一入口 + Artifacts | ArtifactPanel.jsx + artifacts.py | 🟡 Artifacts 完整；导航统一是纯前端工程，未含 |
| 任务6 Kun Provider+MCP | mcp_server.py + §3 | ✅ |

按你 spec 的实施顺序，**阶段1（任务1+省Token前3层）今天就能连通出 MVP**：把 `build_deps` 里 embed 接上、
`SKILL_BASE` 指对、旧端点改裸转发，Kun 指过来即可专业问答 + 省Token生效。

---

## 6. 置信度与待验证假设

| 模块 | 置信度 | 关键假设 |
|---|---|---|
| 编排顺序/管道 | 高 | 上游有独立"裸模型"端点可作 MODEL_UPSTREAM（防递归） |
| Kimi 三级路由 | 高(算法)/中(阈值) | l2_threshold=0.55、ambiguous_gap=0.08 是经验值，需用你真实问题集校准 |
| Kun 省Token | 高(L1/L3/L4/L6)/中(L5) | L5 触发阈 96K、L1 依赖上游支持 prefix caching/X-Prefix-Cache-Key |
| Artifacts | 高 | Kun 端能容忍正文里的 `⟦artifact:id⟧` 短标记（实测应无害；若想更干净，可在 §背景里改为去标记纯文本） |
| MCP | 中 | Kun 支持 MCP-over-HTTP（见 §3 假设） |

**两个我没有、会影响细节的东西**：① reference #6/#7（Kun/Kimi 方法论原文）我只拿到了你 spec 里的*摘要*，
所以 6 层与三级的*接口形态*是按摘要+任务3/4 描述实现的，若原文有更细的参数（如 Storm 的具体阈值曲线、
语义缓存的分桶策略），告诉我可直接对齐。② Kun 是否已有 artifact 渲染能力——这决定 Artifacts 是只在 /app 出，
还是也能回灌 Kun。reference #5「Artifacts+Kun集成方案」我没拿到。

---

需要的话，下一步我可以挑一件**接着写成可直接跑的真东西**：
（a）任务2 的 RAG 入库脚本（bge-m3 + LanceDB，含你那套 source_type/skill_id/standards_ref 的 schema 与元数据标注）；
（b）把 L4 Storm 抑制接进 OpenClaw agent loop 的具体挂法；
（c）任务5 的 `/app` 统一导航（对话|Code|Write|知识库|看板|管理）前端骨架。
