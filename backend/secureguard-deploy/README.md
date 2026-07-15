# SecureGuard — 企业垂类模型五层安全门控系统

为本地部署的垂类模型，在模型前后加装五层防护，确保输出的**安全性、准确性、质量**。
实现对照 `config/arbitration-and-gates.md`（Plane-0，不可改写）。

```
输入 → L0 输入守卫 → L1 仲裁门控 → L2 模型+RAG → L3 输出守卫 → L4 审计 → 用户
       陷阱检测       红线+R2+自省    垂类推理      幻觉检测+脱敏    全链路哈希日志
```

## 设计取舍（重要）

**安全关键的 L0 / L1 / L3 / L4 四层是零第三方依赖的纯标准库实现**，可离线运行、
可被 100% 测试覆盖，不依赖 GPU、网络或任何外部服务。L2（模型 + RAG）被抽象为接口：

- 离线默认：`MockModel` + `InMemoryVectorStore` —— 让整条五层流水线在无 GPU 环境端到端跑通。
- 生产部署：`VLLMModel` + `ChromaVectorStore` —— 真实适配器，检测到依赖与服务时启用。

这样做的理由：安全门控的正确性不应依赖一个可能不可用的重型推理服务。守卫层必须
独立可验证。

## 运行

```bash
# 1) 跑测试（无需 pytest，纯标准库 runner）
python3 run_tests.py
#    若已装 pytest： python3 -m pytest tests/ -v

# 2) 跑效果度量
python3 benchmark/benchmark.py

# 3) 起 HTTP 服务（需 pip install fastapi uvicorn pydantic）
uvicorn secureguard.api:app --port 9000
#    POST /v1/chat {"message": "..."}

# 4) 完整部署（需 GPU 跑 vLLM）
docker compose up
```

当前实测：**35/35 测试通过；红队检出率 100%（44/44），误报率 0%（0/9）。**

## 模块

| 文件 | 层 | 作用 |
|---|---|---|
| `secureguard/l0_input_guard.py` | L0 | 6 类陷阱正则（每类 ≥5 条）+ sanitize + instruction sandwich（含哨兵转义） |
| `secureguard/l1_gate.py` | L1 | 12 红线 + 13 自省触发器 + 6 领域护栏 + gate()/arbitrate() |
| `secureguard/l2_reasoning.py` | L2 | 模型/向量库接口 + Mock + vLLM/Chroma 适配 + RAG + 分步推理 |
| `secureguard/l3_output_guard.py` | L3 | 幻觉信号 + 14 条凭据脱敏 + 质量评分 |
| `secureguard/l4_audit.py` | L4 | 哈希化审计（不存原文）+ 冲突日志 + 红线命中记录 |
| `secureguard/orchestrator.py` | — | 异步串联五层，前置层 BLOCK/ESCALATE 短路 |
| `secureguard/api.py` | — | FastAPI 服务（import-guarded） |
| `config/` | — | Plane-0 只读（红线/护栏/裁决）+ Plane-1 可进化三文件 |
| `red_team_tests/` | — | 53 条红队数据集 + 生成脚本 |
| `benchmark/` | — | 安全/质量/延迟度量 |
| `frontend/ThinkingChain.jsx` | — | 思考过程可视化（步骤卡 + 证伪区 + 置信度） |

## Plane-0 / Plane-1 边界

`config/` 以 **只读（:ro）** 挂载，承载红线、领域护栏、裁决阶梯——任何进化流程都无权改写
（命中红线 R-12）。可进化的只有 `config/plane1/` 的三个惰性数据文件（缺口检查项、规划约束、
预防规则），且必须 append-only。

## 安全自检（对照 megatask 检查清单）

- [x] 测试全绿（`run_tests.py` / `pytest tests/`）
- [x] 红队检出率 > 95%（实测 100%）
- [x] gate() 覆盖全部 12 条红线
- [x] 13 条自省触发器
- [x] 6 个领域护栏
- [x] RAG 管线可独立运行（离线 Mock）
- [x] docker-compose 定义完整五层
- [x] 脱敏覆盖 ≥10 种凭据格式（实测 14）
- [x] 冲突仲裁场景 ≥3（3am 迁移 / CI 关测试 / 礼仪让步）
- [x] 每个公开函数有 docstring
- [x] Plane-0 只读挂载
- [x] 无硬编码密钥 / 无 exec·eval·os.system 处理用户输入 / 无 TODO 占位
