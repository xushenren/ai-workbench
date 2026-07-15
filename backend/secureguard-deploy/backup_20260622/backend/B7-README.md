# B7 — 接真实后端

## 怎么切换
后端按**环境变量**自动选真实/内存后端（`backend/settings.py` + `backend/factory.py`）。
不设环境变量 → 全内存/Mock（开发、沙箱可跑）；设了 → 对应后端切真实，**业务代码与端点零改动**。

```bash
cp backend/.env.example .env && 编辑填真实地址
pip install fastapi uvicorn pydantic httpx chromadb redis asyncpg   # 按需
uvicorn backend.app:app --port 9000
```

## 各后端状态
| 后端 | 适配器 | 接口同源 | 沙箱测试 |
|---|---|---|---|
| 模型 vLLM/LiteLLM | adapters/vllm_model.py | 同 MockModel | ❌ 需 endpoint |
| 向量库 Chroma | adapters/chroma_store.py | 同 InMemoryVectorStore | ❌ 需 chromadb |
| 配额 Redis | adapters/redis_quota.py | 同 QuotaService（Lua 原子） | ❌ 需 Redis |
| 持久化 Postgres | adapters/pg_repos.py（DDL+仓储） | 仓储范式 | ❌ 需 PG |
| 微信 OAuth | adapters/pg_repos.wechat_exchange | 替换 auth 桩 | ❌ 需密钥+网络 |

## 沙箱已验证（test_b7_wiring.py，9 测试）
- 工厂无环境变量时回落内存版；
- 真实适配器与内存版**接口形状一致**（consume/status/recharge/set_limit、add/search、generate）；
- 适配器无依赖库时可导入、实例化报清晰错误；DDL 五张表齐全。

## ⚠️ 必须真机验证
真实模型/向量/Redis/PG/微信的**实际调用全部未测**（沙箱无服务）。逐个接入时：
1. 单独验该后端连通（如 `redis-cli ping`、Chroma `/api/v1/heartbeat`、模型 `/v1/models`）；
2. 设对应环境变量重启，确认 `build_state` 选到真实实现；
3. 跑一次对话，核对行为与内存版一致（尤其配额原子性、检索隔离）。
4. Postgres 接入需把 Auth/Agent/KB 服务内部 dict 换成 pg_repos 仓储调用（签名不变）。
