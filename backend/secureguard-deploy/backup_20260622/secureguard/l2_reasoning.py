"""secureguard.l2_reasoning — L2 推理层（模型 + RAG）。

为了让整条五层流水线在无 GPU、无网络环境也能端到端跑通，本层把模型与
向量库抽象成接口，并提供：
  - MockModel / InMemoryVectorStore：纯标准库实现，离线可跑、行为确定。
  - VLLMModel / ChromaVectorStore：真实部署适配器，仅当依赖与服务可用时启用。
  - RAGPipeline：检索→拼接可信文档→生成，强制来源标注与“无资料则说不知道”。
  - StepwiseReasoner：问题拆解 + 主动证伪 + 置信度，支撑思考过程可视化。
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ====================================================================== #
# 接口与数据类
# ====================================================================== #
@dataclass
class Doc:
    """检索返回的单篇文档。"""

    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class ModelBackend(ABC):
    """语言模型后端接口。"""

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        ...


class VectorStore(ABC):
    """向量库接口。"""

    @abstractmethod
    def search(self, query: str, k: int = 5) -> List[Doc]:
        ...

    @abstractmethod
    def add(self, doc: Doc) -> None:
        ...


# ====================================================================== #
# 离线 Mock 实现（默认）
# ====================================================================== #
class MockModel(ModelBackend):
    """确定性 Mock 模型：离线、可测试。

    根据 prompt 中的标记返回结构化结果：
      - 含 RAG 文档块 → 抽取 [doc_x] 生成带引用的“接地”回答。
      - 含“拆解为” → 返回 JSON 子步骤。
      - 含“主动证伪” → 返回带证伪段的回答。
    """

    def generate(self, prompt: str, **kwargs) -> str:
        # MD 脚手架模式：提示词要求按 <ASSESS>…<ANSWER> 结构输出 → 产结构化段落
        if "<ASSESS>" in prompt and "<ANSWER>" in prompt:
            ids = re.findall(r"\[(doc_\d+)\]", prompt)
            src = ids[0] if ids else None
            gather = (f"已检索到相关条款 [{src}]" if src else "资料未覆盖该问题")
            reason = (f"据此得出关键结论 [{src}]" if src else "现有资料不足以下确切结论")
            verify = ""
            if "<VERIFY>" in prompt:  # 代码领域叠加
                verify = "<VERIFY>未执行验证（需沙箱）。应跑的测试：输入边界/异常路径。</VERIFY>\n"
            if "<VERIFY>" in prompt:
                # 代码场景：ANSWER 含可执行代码块，供沙箱真跑 + 提取为 artifact
                answer = (
                    "这是一个排序函数示例：\n\n"
                    "```python\n"
                    "def sort_list(xs):\n"
                    "    return sorted(xs)\n\n"
                    "print(sort_list([5, 2, 8, 1, 3]))\n"
                    "```\n"
                )
            else:
                answer = (
                    f"根据可信文档，关键结论已标注来源 [{src}]。" if src
                    else "根据现有资料无法确定，建议补充文档或换个问法。"
                )
            return (
                "<ASSESS>信息充分，可作答（无需追问）。</ASSESS>\n"
                f"<GATHER>{gather}</GATHER>\n"
                f"<REASON>{reason}</REASON>\n"
                f"<SELFCHECK>1) 无未标来源的断言 2) 未引用越界来源 3) 置信度 4/5</SELFCHECK>\n"
                f"{verify}"
                f"<ANSWER>{answer}</ANSWER>"
            )
        # 闲聊/打招呼模式（RAGPipeline 判定低相关度时走这里）：自然回应，不强行锚文档
        if "自然、友好地回答" in prompt:
            return (
                "你好！我是企业 AI 工作台的助手。可以问我机电安装规范、施工验收、"
                "或技术概念等问题，我会基于知识库为你解答。\n"
                "（提示：当前为内置占位模型，接入真实模型后回答会更完整。）"
            )
        if "可信文档" in prompt or "retrieved_docs" in prompt or "[doc_" in prompt:
            ids = re.findall(r"\[(doc_\d+)\]", prompt)
            if ids:
                cited = " ".join(f"[{i}]" for i in dict.fromkeys(ids))
                return (
                    f"根据现有可信文档，对该问题的回答如下（每条结论标注来源）：\n"
                    f"- 关键结论 A {ids[0] and '[' + ids[0] + ']'}\n"
                    f"- 关键结论 B {cited}\n"
                    f"若需更精确数值，建议核对来源原文。"
                )
            return "根据现有资料无法确定。"
        if "拆解为" in prompt or "DECOMPOSE" in prompt:
            return json.dumps([
                {"step": 1, "question": "界定输入与约束", "verification": "回读原始需求核对"},
                {"step": 2, "question": "推导核心关系", "verification": "用反例检验单调性"},
                {"step": 3, "question": "汇总并自检边界", "verification": "代入极端值验证"},
            ], ensure_ascii=False)
        if "主动证伪" in prompt or "FALSIFY" in prompt:
            return (
                "【主回答】给出最佳答案与关键假设。\n"
                "【主动证伪】假设1可能错——若X不成立则结论翻转；检验方法：构造反例。\n"
                "【不确定性】置信度 7/10，扣分在数据时效。\n"
                "【查证路径】核对官方文档与一手数据源。"
            )
        return "（mock）已收到查询，返回占位回答。"


class InMemoryVectorStore(VectorStore):
    """基于词重叠打分的内存向量库（离线、确定）。

    生产请替换为 ChromaVectorStore。trust_score 越高的文档排序越靠前，
    实现“可信源优先”的检索语义。
    """

    def __init__(self) -> None:
        self._docs: List[Doc] = []

    def add(self, doc: Doc) -> None:
        self._docs.append(doc)

    @staticmethod
    def _score(query: str, doc: Doc) -> float:
        q = set(re.findall(r"\w+", query.lower()))
        d = set(re.findall(r"\w+", doc.content.lower()))
        if not q or not d:
            overlap = 0.0
        else:
            overlap = len(q & d) / len(q)
        trust = float(doc.metadata.get("trust_score", 0.5))
        # 词重叠为主，可信度为辅
        return overlap * 0.8 + trust * 0.2

    def search(self, query: str, k: int = 5) -> List[Doc]:
        ranked = sorted(self._docs, key=lambda d: self._score(query, d), reverse=True)
        return ranked[:k]


# ====================================================================== #
# 真实部署适配器（仅当依赖可用时启用；本沙箱不会触发）
# ====================================================================== #
class VLLMModel(ModelBackend):
    """vLLM OpenAI 兼容端点适配器。

    依赖：`openai` 客户端 + 运行中的 vLLM 服务（docker-compose 的 model 服务）。
    """

    def __init__(self, base_url: str = "http://model:8001/v1",
                 model: str = "vertical-model", api_key: str = "EMPTY") -> None:
        try:
            from openai import OpenAI  # 延迟导入，缺失不影响离线运行
        except Exception as e:  # pragma: no cover - 依赖缺失路径
            raise RuntimeError("VLLMModel 需要安装 openai 客户端") from e
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    def generate(self, prompt: str, **kwargs) -> str:  # pragma: no cover - 需真实服务
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=kwargs.get("temperature", 0.2),
            max_tokens=kwargs.get("max_tokens", 1024),
        )
        return resp.choices[0].message.content or ""


class ChromaVectorStore(VectorStore):
    """ChromaDB + sentence-transformers 适配器。"""

    def __init__(self, host: str = "vector_db", port: int = 8000,
                 collection: str = "vertical_kb",
                 embed_model: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        try:  # pragma: no cover - 依赖缺失路径
            import chromadb
            from sentence_transformers import SentenceTransformer
        except Exception as e:  # pragma: no cover
            raise RuntimeError("ChromaVectorStore 需要 chromadb + sentence-transformers") from e
        self._client = chromadb.HttpClient(host=host, port=port)
        self._col = self._client.get_or_create_collection(collection)
        self._embed = SentenceTransformer(embed_model)

    def add(self, doc: Doc) -> None:  # pragma: no cover - 需真实服务
        vec = self._embed.encode(doc.content).tolist()
        self._col.add(ids=[doc.id], documents=[doc.content],
                      embeddings=[vec], metadatas=[doc.metadata])

    def search(self, query: str, k: int = 5) -> List[Doc]:  # pragma: no cover
        vec = self._embed.encode(query).tolist()
        res = self._col.query(query_embeddings=[vec], n_results=k)
        out: List[Doc] = []
        for i, content in enumerate(res["documents"][0]):
            meta = res["metadatas"][0][i]
            out.append(Doc(id=meta.get("id", f"doc_{i}"), content=content, metadata=meta))
        return out


# ====================================================================== #
# RAG 管线
# ====================================================================== #
class RAGPipeline:
    """检索增强生成 —— 让模型输出锚定在可信文档上。"""

    RAG_PROMPT = (
        "基于以下可信文档回答问题。如果文档中没有相关信息，必须明确说\n"
        "“根据现有资料无法确定”，不得编造。\n\n"
        "=== 可信文档 ===\n{retrieved_docs}\n\n"
        "=== 用户问题 ===\n{user_question}\n\n"
        "=== 回答要求 ===\n"
        "1. 每条事实陈述后标注来源：[doc_id]\n"
        "2. 如果文档信息不完整，指明缺口\n"
        "3. 禁止引用未在上方出现的文档\n"
        "4. 如果多个文档矛盾，列出矛盾点"
    )

    # 低相关度（打招呼/闲聊/泛问）走这里：自然回答，不强制文档锚定。
    CHAT_PROMPT = (
        "你是企业 AI 助手，请自然、友好地回答用户。下面文档仅供参考——"
        "相关就引用并标注 [doc_id]，不相关就忽略，不要硬扯文档。\n\n"
        "=== 参考文档 ===\n{retrieved_docs}\n\n=== 用户 ===\n{user_question}\n\n助手："
    )

    RELEVANCE_THRESHOLD = 0.2

    def __init__(self, vector_db: VectorStore, model: ModelBackend) -> None:
        self.db = vector_db
        self.model = model

    @staticmethod
    def _relevance(question: str, docs: List[Doc]) -> float:
        """问题与最相关文档的重叠度。中日韩按字、拉丁按词，解决中文整串不分词的问题。"""
        def toks(s: str):
            cjk = set(re.findall(r"[\u4e00-\u9fff]", s))
            latin = set(re.findall(r"[a-zA-Z]+", s.lower()))
            return cjk | latin
        q = toks(question)
        if not q:
            return 0.0
        best = 0.0
        for d in docs:
            inter = len(q & toks(d.content))
            best = max(best, inter / len(q))
        return best

    def query(self, question: str, k: int = 5) -> Dict[str, Any]:
        """检索 top-k（可信源优先）→ 按相关度选锚定/闲聊提示词 → 生成 → 抽取引用。"""
        docs = self.db.search(question, k=k)
        docs = sorted(docs, key=lambda d: d.metadata.get("trust_score", 0), reverse=True)
        joined = "\n\n---\n".join(f"[{d.id}] {d.content}" for d in docs) or "(无检索结果)"
        relevant = self._relevance(question, docs) >= self.RELEVANCE_THRESHOLD
        template = self.RAG_PROMPT if relevant else self.CHAT_PROMPT
        prompt = template.format(retrieved_docs=joined, user_question=question)
        answer = self.model.generate(prompt)
        citations = re.findall(r"\[doc_\d+\]", answer)
        return {
            "answer": answer,
            "sources": [d.metadata | {"id": d.id} for d in docs] if relevant else [],
            "citations": citations,
            "has_grounding": len(citations) > 0,
            "grounded_mode": relevant,
            "retrieved": len(docs),
        }


# ====================================================================== #
# 分步推理器（思考过程可视化的后端）
# ====================================================================== #
class StepwiseReasoner:
    """问题拆解 + 逐步求解 + 主动证伪 + 置信度，输出可视化推理链。"""

    DECOMPOSE_PROMPT = (
        "将以下复杂问题拆解为 3-5 个可独立验证的子步骤。每个子步骤应原子化、"
        "可检验。仅输出 JSON 数组：[{{\"step\":1,\"question\":\"子问题\","
        "\"verification\":\"如何验证\"}}]\n\n问题：{question}"
    )
    FALSIFY_PROMPT = (
        "你是{domain}领域专家。对子问题：{question}\n"
        "1.【主回答】给出最佳答案与关键假设\n"
        "2.【主动证伪】列 2-3 个可能错的假设，各给推翻方法与“若错则正确答案”\n"
        "3.【不确定性】1-10 打分并说明扣分点\n"
        "4.【查证路径】指出需查的数据源与关键词"
    )

    def __init__(self, model: ModelBackend) -> None:
        self.model = model

    def _safe_json(self, text: str, default: Any) -> Any:
        """容错解析模型 JSON 输出，剥离可能的代码围栏。"""
        cleaned = re.sub(r"```(?:json)?|```", "", text).strip()
        try:
            return json.loads(cleaned)
        except Exception:
            return default

    def reason(self, question: str, domain: str = "general") -> Dict[str, Any]:
        """返回可视化推理链：每步含答案、证伪、置信度、耗时占位。"""
        import time

        steps_spec = self._safe_json(
            self.model.generate(self.DECOMPOSE_PROMPT.format(question=question)),
            default=[{"step": 1, "question": question, "verification": "直接核对"}],
        )
        chain: List[Dict[str, Any]] = []
        for spec in steps_spec:
            t0 = time.time()
            sub_q = spec.get("question", question)
            falsify = self.model.generate(self.FALSIFY_PROMPT.format(domain=domain, question=sub_q))
            answer = self.model.generate(sub_q)
            confidence = self._estimate_confidence(answer, falsify)
            chain.append({
                "id": spec.get("step", len(chain) + 1),
                "label": sub_q[:24],
                "status": "completed",
                "question": sub_q,
                "answer": answer,
                "falsify": falsify,
                "verification": spec.get("verification", ""),
                "confidence": confidence,
                "duration_ms": int((time.time() - t0) * 1000),
            })
        overall = round(sum(c["confidence"] for c in chain) / max(len(chain), 1), 3)
        return {
            "steps": chain,
            "final_answer": self._synthesize(chain),
            "overall_confidence": overall,
        }

    @staticmethod
    def _estimate_confidence(answer: str, falsify: str) -> float:
        """启发式置信度：答案含不确定词或证伪暴露翻转风险则降低。"""
        conf = 0.85
        if re.search(r"无法确定|不确定|可能|也许|大概", answer):
            conf -= 0.25
        if re.search(r"翻转|不成立|反例", falsify):
            conf -= 0.1
        return round(max(0.1, min(conf, 0.99)), 3)

    @staticmethod
    def _synthesize(chain: List[Dict[str, Any]]) -> str:
        if not chain:
            return "（无可综合的步骤）"
        return "综合各子步骤：" + "；".join(c["label"] for c in chain)
