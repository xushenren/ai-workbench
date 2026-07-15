# CONTRACT.md — Phase 0 契约冻结（企业 AI 工作台）

> 前后端并行开工前冻结的单一事实源。改动须走评审，禁止单边变更。
> 配套已落地代码：红线 19/自省 18（`l1_gate.py`）、审计哈希链（`l4_audit.py`）、
> trace 双轨（`trace.py`）、算力 policy 路由（`compute_router.py`）。

---

## 1. 红线权威清单（D1）

19 条，编号 R-01..R-19。R-01..R-12 见 `l1_gate.REDLINES`，R-13..R-19 为企业扩展：

| 编号 | 名称 |
|---|---|
| R-13 | 跨租户/越权访问他人私有库或会话 |
| R-14 | 敏感数据路由/外发出企业边界 |
| R-15 | 篡改/绕过配额或计费 |
| R-16 | 未脱敏 PII 入日志/思考面板/外部 |
| R-17 | 未审批的批量用户数据导出 |
| R-18 | 改/删他人会话、数据、智能体 |
| R-19 | 注入层外提权/覆盖 CONSTITUTION |

> 待办：R-13..R-19 的措辞与 Constitution v2 逐条核对（覆盖面与编号已对齐）。
> 自省触发器同步到 18 条，见 `l1_gate.SELF_MONITOR_TRIGGERS`。

---

## 2. REST API 契约

```
POST /v1/chat                 发起对话（非流式回退）
WS   /v1/stream               流式对话 + 思考过程帧
GET  /v1/agents               智能体列表（按可见性过滤）
POST /v1/admin/agents         创建/更新智能体（admin/developer）
GET  /v1/quota/{agent_id}     查询配额
GET  /v1/audit/verify         触发哈希链校验（admin）
POST /v1/kb/search            知识库检索（带身份，强制隔离）
```

### POST /v1/chat 请求
```jsonc
{
  "message": "string",
  "session_id": "string",
  "agent_id": "string",
  "caller": { "user_id": "u1", "role": "user", "dept_id": "d1" }
}
```
### 响应（放行 / 拦截）
```jsonc
{ "blocked": false, "answer": "...", "citations": ["[doc_1]"],
  "tier": "tier1", "public_trace": [ /* 见 §4 */ ], "latency_ms": 42 }
{ "blocked": true, "stage": "L0|L1", "display": "⛔ 已被安全策略拦截" }
// 注意：拦截响应对用户不回显 rule_id（仅审计留存）
```

---

## 3. WS 流式帧

```jsonc
// 思考过程帧（逐帧推送 public_trace，见 §4）
{ "event": "trace", "frame": { "stage":"tool","type":"tool_call","display":"✓ ..." } }
// 增量答案
{ "event": "delta", "text": "..." }
// 结束
{ "event": "done", "tier":"tier1", "latency_ms": 1240 }
```

---

## 4. 思考过程双轨 schema（D3）

每个原始帧 `TraceFrame`（`trace.py`）拆成两份。**字段去向**：

| 字段 | public_trace（用户/前端） | audit_trace（admin+审计表） |
|---|:---:|:---:|
| stage / type | ✓ | ✓ |
| display（脱敏后人读串，永不空白） | ✓ | — |
| status（PASS/BLOCK 粗粒度） | ✓（gate 帧） | — |
| tool_name | ✓ | ✓ |
| params | ✓ 脱敏后 | — |
| params_hash / result_hash | — | ✓ |
| result | ✓ 脱敏后（全脱敏则隐藏+计数说明） | — |
| result_count | ✓ | ✓ |
| **rule_id** | ✗ 绝不下发 | ✓ |
| tier | ✓ | ✓ |
| latency_ms | ✓ | ✓ |
| session_id | — | ✓ |

**脱敏流程（每帧渲染前）**：tool 的 params/result → `OutputGuard.check()` → `sanitized_output`。
**全脱敏降级**：返回值被洗空时，public 显示
`"✓ 工具 X 调用完成，返回 N 条结果（含隐私信息，已按隐私策略隐藏）"`——让用户知道"成功且被保护"，而非以为系统坏了。

---

## 5. DB schema（核心表）

```sql
-- 用户与角色（Q1）
users(id, phone, wechat_openid, role,           -- admin/developer/user
      dept_id, dept_admin BOOLEAN, created_at)

-- 智能体（含 D2 compute_policy / D6 scope）
agents(id, name, description, domain, system_prompt,
       model, fallback_model,
       compute_policy JSONB,        -- {allowed_tiers, preferred_order, force_local_for, fail_strategy}
       scope TEXT,                   -- "domain_only" / "open"
       free_quota JSONB,             -- {monthly_tokens, freeze_period}
       visibility TEXT,              -- public/department/private
       owner_id, status,             -- draft/pending_review/published
       created_at)

-- 配额（D6，并发原子扣减走 Redis，PG 为持久化对账）
quotas(user_id, agent_id, period, used_tokens, limit_tokens,
       locked BOOLEAN, freeze_until, UNIQUE(user_id, agent_id, period))

-- 审计（D5 哈希链）
audit(id BIGSERIAL, session_id, stage, decision, reason,
      input_hash, output_hash, rule_id, tier, latency_ms,
      prev_hash CHAR(64), entry_hash CHAR(64),   -- 哈希链字段
      created_at)

-- 知识库（D7 隔离）
knowledge_bases(id, name, type,                   -- public/department/private
                tenant_id, visibility, owner_id, allowed_roles JSONB,
                dept_id, created_at)
documents(id, kb_id, content_hash, vector_ref, metadata JSONB)
```

**检索隔离铁律（D7）**：`/v1/kb/search` 必须带 `caller`，查询条件下推为
`visibility='public' OR (type='department' AND dept_id=:caller_dept) OR owner_id=:caller_id`，
**绝不在应用层过滤后才隔离**。管理员可管理但 `private` 库只存哈希、不可见原文。

---

## 6. Agent 配置 schema（D2 + D6）

```yaml
agent:
  name: "HR助手"
  domain: "hr"
  scope: "domain_only"             # D6：只答本领域，越界拒绝（C4 校验）
  compute_policy:                   # D2：管理员按业务分配算力
    allowed_tiers: [tier1]          # 员工隐私不出内网
    preferred_order: [tier1]
    force_local_for: [R0, R1]
    fail_strategy: closed
  free_quota: { monthly_tokens: 10000, freeze_period: monthly }
  visibility: public
  guardrails: { redlines: all, self_monitor: true, domain_guard: hr }
```
配额耗尽行为（D6）：允许负数（不中断当前请求）→ 余额≤0 锁定该智能体（对此用户）
→ 等冻结重置 或 充值即时解锁。

---

## 7. 待澄清项的处置（见随附答复）

- **Q1 角色边界（已锁定，编码于 `permissions.py`，14 测试通过）**：
  - `admin` 全局：审批上线、管理全部、管理任意配额。
  - `department_admin` 部门：管本部门知识库与本部门用户配额；**看不到成员私人库原文**。
  - `developer` 可建智能体；建**私有**不需审批；要**多人可见**(部门/公共)须 **admin 审批上线**
    （`draft→pending_review→published`，可 `rejected→draft` 打回重提）。
  - `user` 可建**私人智能体**（visibility=private，仅自己、不进市场、不需审批，直接 published）。
  - 可选开关：把【部门可见】审批权下放给对应 `department_admin`
    （`can_approve` 内 `DELEGATE_DEPT_APPROVAL_TO_DEPT_ADMIN`，默认关，严格对齐"须 admin 审批"）。
- **Q2 与现有体系关系**：属你方产品决策，本契约不预设；但 SecureGuard 作为独立安全层，
  EVA/OKComputer 若接入应统一走同一 `/v1/chat` 安全代理，避免各做一套护栏。
- **Q3 部署形态**：按 **A（单企业独立部署）** 落地，`tenant_id` 字段预留但多租户逻辑不激活。
