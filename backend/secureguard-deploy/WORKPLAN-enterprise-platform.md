# 企业 AI 工作台 — 工作方案

> 这份方案不是把规格 §12 那句"一次生成完整前后端+部署"照单执行——那既不现实
> 也无法在任何沙箱里验证。它做三件事：**① 把必须先拍板、否则后面返工的设计决策挑出来；
> ② 排出可分阶段、每阶段独立可测的路线图；③ 标清哪些能直接复用已建好的 SecureGuard。**
>
> 锚点已落地：规格里最大的安全隐患（敏感数据经 Tier 3 出境）已写成可测代码
> `secureguard/compute_router.py`（11 个测试全过），作为本方案"决策 D2"的实现样板。

---

## 一、必须先拍板的 7 个决策（动代码前）

这些不定，后面每一层都得返工。按重要性排序。

### D1 · 红线/自省的"权威数量"不一致 —— 先统一单一事实源
规格里写 **19 条红线 / 18 自省**，但已落地的 SecureGuard 是 **12 红线 / 13 自省**，
Constitution v2 又是另一套。**先把这三处对齐到一份权威清单**（建议以 Constitution v2 为准，
SecureGuard 的 `REDLINES`/`SELF_MONITOR_TRIGGERS` 补齐到 19/18）。不对齐的话，
智能体配置里 `redlines: all` 到底是几条都说不清，审计"红线触发 0 次"也失去意义。
→ 动作：产出 `config/redlines.yaml` 权威版（19 条），代码常量与之逐条对照测试。

### D2 · 算力路由的数据出境（最高优先级）✅ 已给样板
规格 Tier 3 是 **OpenAI/DeepSeek/Claude 等外部 API**，而产品定位"部署在企业自有服务器"。
**敏感/PII 数据一旦自动降级到 Tier 3 就出境，直接违反红线 R-10。** 这不是边缘情况——
"Tier 1→2→3 自动降级"是规格的默认行为，内网一抖动就可能把身份证、密钥、内部文档发给外部 API。
→ 已实现 `compute_router.py`：**先数据分级（PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED），
再按分级决定允许的最高 Tier**。RESTRICTED/CONFIDENTIAL 禁止外部 API；内网全挂时
**fail-closed 拒绝，绝不偷偷出境**。注意我顺手补了**中国身份证/手机号/银联卡** PII 模式——
规格里默认的美式 SSN 在这儿没用。这一条建议**第一个并入主干**。

### D3 · "思考过程可见" vs "不回显命中哪条护栏" 的张力
规格 §5 要把"调用了哪些 Tool/Skill（**参数和返回值可见**）""过了哪些门"实时展示给用户。
两个隐患：
- **工具返回值直出会泄密**：某 Tool 读了私有知识库或返回了含 PII 的结果，原样显示在思考面板=
  绕过了所有输出守卫。→ 思考面板的每一帧必须过 **L3 OutputGuard 脱敏**后再渲染。
- **回显具体红线 id 给攻击者反馈**：显示"R-07 红线检测 PASS/BLOCK"等于告诉攻击者你有哪些规则、
  怎么调输入绕过。→ 对**普通用户**只显示"安全检查通过/被拦截"，**具体 rule id 仅写审计、
  仅 admin 可见**。
→ 动作：思考面板数据分两份——`public_trace`（脱敏、不含 rule id）给用户，
`audit_trace`（完整）只进审计。

### D4 · 敏感任务 Tier 1 不可用时：fail-closed 还是排队？
规格说"敏感任务强制 Tier 1 不降级"，但没说 Tier 1 挂了怎么办。两种合理策略，**必须显式选**：
fail-closed 立即拒绝（安全最高）/ 入队等 Tier 1 恢复（可用性优先，但要给用户超时反馈）。
→ `compute_router.py` 当前实现的是 **fail-closed**（`force_local` 且 Tier1 不可用 → 拒绝）。
若你要"排队"语义，加一个 `QUEUED` 决策态即可，逻辑已留好位置。

### D5 · 审计"不可篡改"——append-only 不等于不可篡改
规格 §13.4"审计不可篡改受 R-09 保护"。但当前 `l4_audit.py` 是 append-only JSONL，
**能被有文件权限的人改**。真正的防篡改要**哈希链**：每条记录含上一条的哈希，
改任意一条都会断链、可被检出。
→ 动作：给 `AuditEntry` 加 `prev_hash` 字段，写入时 `entry.prev_hash = last_entry_hash`，
提供 `verify_chain()`。这是 D 类里最便宜、收益最大的强化，半天能做完且可测。

### D6 · 配额扣减的并发原子性
规格 §7 免费额度 + 冻结。**并发请求下"剩余 token"是竞态热点**：两个请求同时读到剩余 100，
各扣 80，结果透支。→ 必须用 **Redis 原子操作**（`DECRBY` + Lua 脚本判断）或 PG 行锁，
绝不能"读-改-写"。这条决定数据库选型里 Redis 的角色。

### D7 · 多租户知识库的强隔离
规格 §8 知识库分 public/dept/private。**检索时的权限过滤不能只在应用层做**——
向量库查询必须带 `tenant_id`/`visibility` 过滤条件下推到存储层，否则一次 prompt injection
就可能让用户检索到别人的私有库。→ 向量库 schema 从第一天就带隔离字段，
检索接口强制传调用者身份。

---

## 二、复用地图 —— 别重写已有的

规格 §12.4 明确"`backend/guards/` 可直接复用 SecureGuard"。实际能复用的比这更多：

| 规格组件 | 已有资产 | 状态 |
|---|---|---|
| backend/guards/ 19 红线·自省·护栏 | `l0_input_guard` `l1_gate` | ✅ 在，需把 12→19 / 13→18 补齐 |
| 版权/检索护栏 | `retrieval_guard.py` | ✅ 已测 |
| Harness 授权门 gate()/arbitrate() | `l1_gate.py` | ✅ 已测，含仲裁阶梯 |
| Loop 进化五道门 G1-G5 | `evolution_gates.py` + `refiner-prompt.md` | ✅ 已测 |
| L4 审计哈希化 | `l4_audit.py` + `audit_rotation.py` | ✅ 在，需加 D5 哈希链 |
| 安全代理可用性（fail-closed/熔断） | `safety_proxy.py` | ✅ 已测 |
| **算力路由 + 数据分级门** | `compute_router.py` | ✅ **本次新增，已测** |
| 思考过程数据结构 | `orchestrator.process()` 的 `steps[]` + `StepwiseReasoner` | ✅ 在 |
| 思考面板 UI | `frontend/ThinkingChain.jsx` | 🟡 雏形，需扩为流式 + 脱敏 |
| RAG 检索 | `l2_reasoning.RAGPipeline` + Chroma 适配 | ✅ 在 |
| 多模型统一接口（LiteLLM 角色） | `l2_reasoning.ModelBackend` 抽象 | ✅ 接口已留，补适配器即可 |

**结论：后端"安全 + 推理管道 + 路由"的内核已经有 ~70%，真正要从零做的是
业务外壳（认证/配额/知识库/智能体管理）和前端。**

---

## 三、分阶段路线图（每阶段独立可测 + 可演示）

每个阶段标注**可测性**：🟢离线可测 / 🟡仅可渲染或部分测 / 🔴需真实服务（PG/Redis/微信/GPU）真机验收。

### Phase 0 · 契约冻结（1 阶段，纯文档，最该先做）🟢
冻结三套 schema，后面前后端并行才不会对不上：
- **API/WS 契约**：`POST /v1/chat`、`WS /v1/stream`（思考过程帧格式）、admin CRUD。
- **事件 schema**：思考面板每一帧的结构（`{stage, type, public_trace, ...}`）。
- **DB schema**：users / agents / quotas / audit（含 `prev_hash`）/ knowledge_bases（含 `tenant_id,visibility`）。
- 解决 D1（红线权威清单）、D3（trace 双份）、D7（隔离字段）。
> 验收：schema 评审通过 + 用 mock 数据跑通契约校验。

### Phase 1 · 后端推理管道主干（复用 SecureGuard）🟢
把 `orchestrator` 扩成真实请求路径：Context(C1-C4) → Harness(gate) → Loop(L1-L5)，
模型用 Mock，端到端可测。产出 `public_trace`/`audit_trace` 双轨。
> 验收：现有 64 测试 + 新增管道集成测试全绿；一次请求能打出完整 steps[]。

### Phase 2 · 算力路由 + 数据分级门 ✅ 已起步 🟢
并入 `compute_router.py`，接到管道里：每次请求先分级 → 路由 → 把选中的 Tier 标进 trace。
补 Tier 1/2/3 的真实 backend 适配（vLLM / 私有云 / LiteLLM），适配器 import-guard。
> 验收：分级门 11 测试已过；加"敏感请求被挡在外部 API 外"的端到端用例。

### Phase 3 · 配额计费 + 审计强化 🔴(配额需 Redis)
- 配额：Redis 原子扣减（D6）+ 冻结窗口 + 80/90/100% 预警 + 四维统计。
- 审计：哈希链（D5）+ `verify_chain()` + 轮转（已有 `audit_rotation`）。
> 验收：审计链篡改检测可测（🟢）；配额并发扣减需起 Redis 真机压测（🔴）。

### Phase 4 · 智能体 / Skill / Tool 引擎 + MCP 🟡
- Agent 定义加载（规格 §9 YAML）→ 注入系统提示词（§11 结构）。
- Tool 调度对齐 MCP；Skill runtime。
- 内置智能体：通用助手 + 机电安装助手（339 标准引用校验，复用 `retrieval_guard` 做引用合规）+ 2 个垂类。
> 验收：Agent 配置→提示词注入可测（🟢）；真实 Tool 调用需对应服务（🔴）。

### Phase 5 · 前端：聊天主界面 + 思考面板（流式）🟡
- 聊天窗口（Markdown/代码高亮/文件预览）+ 左侧会话/智能体/知识库。
- **思考面板订阅 WS，逐帧渲染 `public_trace`**（扩展 `ThinkingChain.jsx`）。
> 验收：组件可渲染、对 mock 帧流可演示（🟡）；真实交互需后端联调。

### Phase 6 · 前端：Agent Store + Admin 🟡
卡片市场 + 后台（用户/智能体/模型/路由/配额/审计/知识库）。

### Phase 7 · 认证 + 知识库 🔴
手机号注册 + 微信扫码 OAuth（需真实 AppID/回调）；文档上传→分段→向量化。
> 这是**沙箱完全测不了**的部分，验收标准必须写成"真机连真微信/真 PG 跑通"。

### Phase 8 · 部署 + 监控 🔴
docker-compose（单机）/ K8s（集群）+ Prometheus/Grafana + `.env.example` + README。
Plane-0 配置只读挂载（:ro）。

---

## 四、风险登记（Top 风险 + 缓解）

| 风险 | 后果 | 缓解 | 状态 |
|---|---|---|---|
| 敏感数据经 Tier 3 出境 | 违反 R-10、合规事故 | 数据分级门 fail-closed | ✅ 已实现 |
| 思考面板泄露工具返回值/PII | 绕过输出守卫 | trace 过 L3 脱敏；rule id 仅 admin | 🟡 D3 待落 |
| 审计可被篡改 | "不可篡改"名不副实 | 哈希链 + verify_chain | 🟡 D5 待落 |
| 配额并发透支 | 计费漏洞 | Redis 原子扣减 | 🟡 D6 待落 |
| 跨租户检索私有库 | 数据越权 | 隔离字段下推 + 强制身份 | 🟡 D7 待落 |
| 一次性生成全平台 | 不可测、必返工 | 分阶段、每阶段可验收 | ✅ 本方案 |
| 微信/PG/GPU 沙箱不可测 | 误以为"已交付"实则没验 | 标 🔴 + 真机验收标准 | ✅ 已标注 |
| 红线数量三处不一致 | 配置/审计语义混乱 | D1 单一事实源 | 🟡 D1 待落 |

---

## 五、建议的下一步

内核已有 ~70%，我建议**按 Phase 0→1→2 推进**，因为这三阶段全部 🟢 离线可测、且把
最危险的数据出境问题（D2，已起步）和契约/审计/隔离的地基（D1/D3/D5/D7）钉死。
业务外壳和前端（Phase 4-8）含大量 🔴 不可测部分，应在地基稳固后再做，且交付时
**诚实区分"已测"与"需真机验收"**。

我可以直接开工的、当下就能做成**离线可测代码**的选项（挑一个我就开始）：
1. **Phase 1 推理管道主干** —— 把 orchestrator 扩成 Context→Harness→Loop 真实路径 + trace 双轨。
2. **D5 审计哈希链** —— 给 AuditEntry 加 prev_hash + verify_chain，半天级、立即可测。
3. **D1 红线补齐** —— 把 12 红线扩到权威 19 条并逐条测试。
4. **把 compute_router 接进 orchestrator** —— 让分级路由进入真实请求流并出现在 trace 里。

认证、微信 OAuth、完整前端这类 🔴 部分我也能写，但会**明确标注未经真机测试**，
不会假装跑通过。
