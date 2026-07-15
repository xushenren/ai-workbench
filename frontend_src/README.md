# 企业 AI 工作台 — 前端

React 18 + TypeScript + Vite + Tailwind + Zustand。对接 CONTRACT.md 契约与后端 `:9000`。
视觉走 **Claude.ai 气质**：暖中性底 + 陶土橙强调，明暗双主题，思考面板克制灰阶（仅 BLOCK 用警示色）。

## 运行

```bash
npm install
npm run dev        # http://localhost:5173 ，/v1 与 ws 自动代理到 :9000
npm run build      # tsc -b + vite build
npm run typecheck  # 仅类型检查
```

后端没起也能跑：所有数据 fallback 到内置示例，顶部显示「后端服务未连接 · 当前为演示数据」，
聊天会走**离线演示模式**（模拟思考帧 + 流式答案），界面不白屏。

## 页面

| 路由 | 内容 |
|---|---|
| `/chat` | 三栏：左侧会话/知识库/算力 · 中间聊天(Markdown+代码高亮+流式光标) · 右侧思考面板 |
| `/agents` | 智能体市场：全部/公共/部门/我的 Tab + 卡片网格 |
| `/admin` | 6 统计卡 + 模型配置/Token配额/安全门控/最近审计 4 面板 |
| `/login` | 手机号+密码 + 微信扫码占位，明暗自适应 |

## 对接后端

- REST：`/v1/agents` `/v1/agents/:id` `/v1/knowledge` `/v1/compute/status` `/v1/admin/stats` `/v1/auth/login`（`lib/api.ts`）
- WebSocket：`/v1/chat/stream`，发 `{message, agent_id, session_id}`，收 `trace/delta/done` 帧（`lib/ws.ts`）
- 开发期跨域由 `vite.config.ts` 的 proxy 解决，生产改 `BASE` 与 `wsUrl()` 为绝对地址。

## 安全约束的落地（对应 CONTRACT.md / 关键约束）

- **思考面板结构上不可能渲染 rule_id**：`PublicTraceFrame` 类型**根本不含** rule_id/内部参数字段，只渲染 `display`。
- **拦截不回显具体原因**：`status:"blocked"` 只显示「已被安全策略拦截」。
- **不使用 localStorage/sessionStorage**：状态全在 Zustand 内存（主题切换亦然，刷新重置为亮色——刻意遵守该约束）。
- **TypeScript 严格模式**，props 均有接口。

## 设计说明

- 配色：亮色暖象牙 `#F5F4EE` / 深色暖炭 `#262624`，强调陶土橙 `#C96442`，全部经 CSS 变量做明暗双主题。
- 字体：标题 Newsreader(文学衬线)，正文 Inter + Noto Sans SC，代码 JetBrains Mono；无网络回退系统字体。
- 思考面板**没有用 spec 原定的五彩阶段色**——按 Claude 审美降为灰阶 + 图标 + 单强调色，仅 BLOCK 用警示红，更安静。

## ⚠️ 诚实的交付边界（必读）

**本前端未经构建/运行验证。** 生成环境网络隔离、装不了 npm 依赖，无法跑 `tsc`/`vite build`/真机渲染。
我做了的静态校验：JSON 配置合法、16 个 `@/` 引用全部解析到位、`React.ReactNode` 缺导入等
2 处必挂错误已修、未使用导入已清零。但**类型推断细节、第三方库的精确 API、运行时渲染、
与真实后端的联调，必须你在真机验证**。

### 你的自验清单
1. `npm install` —— 若某依赖版本拉不到，按报错调 `package.json` 版本。
2. `npm run typecheck` —— 严格模式下若有残留类型问题，这里会暴露（最可能在
   `react-syntax-highlighter` 的 style 类型、`react-markdown` v9 的 `code` 渲染签名）。
3. `npm run dev` —— 先不连后端，确认三页面 + 离线演示 + 明暗切换正常。
4. 起后端 `:9000` 后，确认 WS 帧能正确驱动思考面板、流式 token 追加到同一气泡。
5. 重点回归安全约束：故意让后端 trace 带 rule_id，确认前端**不显示**（类型已挡，但端到端再确认一次）。
