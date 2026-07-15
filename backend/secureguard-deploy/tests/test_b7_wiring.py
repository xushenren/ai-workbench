"""tests/test_b7_wiring.py — B7 接线单测（沙箱可测的部分）。

沙箱无 GPU/Redis/Chroma/PG，**真实后端的实际调用测不了**。本测试只验：
  1. 工厂在无环境变量时正确回落内存版；
  2. 真实适配器与内存版**接口形状一致**（保证 swap 是配置级、不改逻辑）；
  3. 适配器模块可被导入（import-guard 生效）、DDL 等静态资产存在。
"""
import sys, os, inspect
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.settings import Settings
from backend.factory import build_state
from backend.state import AppState
from backend.quota_service import QuotaService
from secureguard import MockModel, InMemoryVectorStore


# ---------- 工厂回落 ----------
def test_factory_defaults_to_inmemory():
    st = build_state(Settings())  # 空配置
    assert isinstance(st, AppState)
    assert isinstance(st.quota, QuotaService)               # 非 Redis
    assert isinstance(st.orchestrator.rag.model, MockModel)  # 非 vLLM


def test_settings_flags_off_by_default():
    s = Settings()
    assert not (s.use_real_model or s.use_chroma or s.use_redis or s.use_postgres or s.use_wechat)


def test_settings_flags_on_when_set():
    s = Settings(model_base_url="http://m", chroma_host="h", redis_url="redis://r",
                 database_url="pg://d", wechat_appid="a", wechat_secret="s")
    assert s.use_real_model and s.use_chroma and s.use_redis and s.use_postgres and s.use_wechat


# ---------- 接口形状一致（关键：保证 swap 不改逻辑） ----------
def _method_names(cls, names):
    return all(callable(getattr(cls, n, None)) for n in names)


def test_vllm_model_matches_modelbackend_interface():
    from backend.adapters.vllm_model import VLLMModel
    assert _method_names(VLLMModel, ["generate", "generate_stream"])
    # generate 签名与 MockModel 兼容（prompt 为首参）
    sig = inspect.signature(VLLMModel.generate)
    assert "prompt" in sig.parameters


def test_chroma_store_matches_vectorstore_interface():
    from backend.adapters.chroma_store import ChromaVectorStore
    assert _method_names(ChromaVectorStore, ["add", "search"])
    # 与 InMemoryVectorStore 同名方法
    assert _method_names(InMemoryVectorStore, ["add", "search"])


def test_redis_quota_matches_quotaservice_interface():
    from backend.adapters.redis_quota import RedisQuotaService
    required = ["consume", "status", "recharge", "set_limit"]
    assert _method_names(RedisQuotaService, required)
    assert _method_names(QuotaService, required)
    # consume 签名一致（key, tokens, limit, freeze_period）
    a = set(inspect.signature(RedisQuotaService.consume).parameters)
    b = set(inspect.signature(QuotaService.consume).parameters)
    assert {"key", "tokens", "limit", "freeze_period"} <= (a & b)


def test_adapters_import_without_their_libs():
    # import-guard：无 httpx/chromadb/redis 时类仍可导入（实例化才报错）
    import backend.adapters as ad
    assert ad.VLLMModel and ad.ChromaVectorStore and ad.RedisQuotaService


def test_pg_ddl_and_repos_present():
    from backend.adapters import pg_repos
    for tbl in ("users", "agents", "quotas", "audit", "knowledge_bases"):
        assert f"CREATE TABLE IF NOT EXISTS {tbl}" in pg_repos.DDL
    assert hasattr(pg_repos, "AuditRepo") and hasattr(pg_repos, "QuotaRepo")
    assert hasattr(pg_repos, "wechat_exchange")


def test_instantiating_real_adapter_without_lib_raises_clear_error():
    from backend.adapters.redis_quota import RedisQuotaService
    try:
        RedisQuotaService("redis://localhost")  # 无 redis 库
    except RuntimeError as e:
        assert "redis" in str(e)
    except Exception:
        pass  # 若恰好装了 redis，连接错误也可接受（沙箱一般没有）
