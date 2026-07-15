"""
expert_router.py — Kimi 多专家系统方法论的落地（专家路由 / 难度分级 / Skill 注入）

三级召回（对应 spec 任务3）：
  L1 规则匹配   TF-IDF/关键词   <1ms   命中即定路由
  L2 语义路由   bge-m3 + 余弦    ~10ms  取 top Skill；不确定则多 Skill 并行
  L3 LLM 确认   小模型一次判定   ~300ms 仅在 L1/L2 置信度不足时触发

输出：选中的 skill_id 列表 + 注入用的 System Prompt（含 Artifacts 产出约定）。
专家库 = 14 专业基座 Skill × 14 行业适配 × 15 交叉专项，统一抽象为 Expert。
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


# --------------------------------------------------------------------------- #
# 专家定义：把 Skill / 行业 / 交叉统一成 Expert
# --------------------------------------------------------------------------- #
@dataclass
class Expert:
    id: str
    name: str
    kind: str                     # "skill" | "industry" | "cross"
    keywords: list[str]           # L1 规则匹配用
    system_prompt: str            # 命中后注入
    depth: int = 3                # ●●●=3 / ●○○=1，难度分级与质量预期用
    embedding: Optional[list[float]] = None  # L2 语义匹配用（延迟计算）


@dataclass
class RouteResult:
    experts: list[Expert]
    level: str                    # "L1" | "L2" | "L3" | "fallback"
    confidence: float
    difficulty: str               # "easy" | "medium" | "hard"
    injected_system: str


# --------------------------------------------------------------------------- #
# 专家库加载：从 spec 第六节给的路径读取 Skill 文件
# --------------------------------------------------------------------------- #
class ExpertRegistry:
    """
    约定目录结构（按你方实际路径调整 base）：
      base/skills/01-管道施工.md ... 14-园林绿化.md
      base/industry/*.md
      base/cross/*.md
    每个文件 frontmatter 可含 keywords；缺省时用文件名 + 标题抽取关键词。
    """

    def __init__(self, base: str | Path, embed: Optional[Callable[[str], list[float]]] = None):
        self.base = Path(base)
        self.embed = embed
        self.experts: dict[str, Expert] = {}

    def load(self) -> "ExpertRegistry":
        for kind, sub in (("skill", "skills"), ("industry", "industry"), ("cross", "cross")):
            d = self.base / sub
            if not d.exists():
                continue
            for f in sorted(d.glob("*.md")):
                meta, body = self._parse(f.read_text(encoding="utf-8"))
                eid = meta.get("id") or f.stem
                self.experts[eid] = Expert(
                    id=eid,
                    name=meta.get("name", f.stem),
                    kind=kind,
                    keywords=meta.get("keywords") or self._auto_keywords(f.stem, body),
                    system_prompt=body.strip(),
                    depth=int(meta.get("depth", 3)),
                )
        # 预计算 embedding（若注入了 bge-m3）
        if self.embed:
            for e in self.experts.values():
                e.embedding = self.embed(e.name + " " + " ".join(e.keywords))
        return self

    @staticmethod
    def _parse(text: str) -> tuple[dict, str]:
        if text.startswith("---"):
            _, fm, body = text.split("---", 2)
            meta = {}
            for line in fm.strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    v = v.strip()
                    meta[k.strip()] = json.loads(v) if v.startswith("[") else v
            return meta, body
        return {}, text

    @staticmethod
    def _auto_keywords(stem: str, body: str) -> list[str]:
        # 取文件名分词 + 正文高频中文双字词，作为兜底关键词
        base = re.findall(r"[\u4e00-\u9fa5]{2,}", stem)
        grams = re.findall(r"[\u4e00-\u9fa5]{2,4}", body[:2000])
        common = [w for w, _ in Counter(grams).most_common(12)]
        return list(dict.fromkeys(base + common))


# --------------------------------------------------------------------------- #
# 三级召回路由
# --------------------------------------------------------------------------- #
def _cosine(a, b) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# Artifacts 产出约定：注入到每个专家 System Prompt 末尾，让模型知道何时产出 artifact
ARTIFACT_PROTOCOL = """

【产出规范】当回答包含可独立保存/复用的成果（>20 行代码、施工方案、计算书、表格、流程图、清单），
用如下围栏包裹，便于平台抽取为 Artifact；普通解释性文字保持正文，不要包裹：
```artifact:{type} title="标题"
<内容>
```
type ∈ code|markdown|table|mermaid|calc。每个 artifact 自带完整上下文，可脱离对话独立阅读。
"""


@dataclass
class ExpertRouter:
    registry: ExpertRegistry
    embed: Optional[Callable[[str], list[float]]] = None      # bge-m3
    llm_confirm: Optional[Callable[[str, list[Expert]], str]] = None  # 小模型确认，返回 expert_id
    l1_min_hits: int = 2
    l2_threshold: float = 0.55
    l2_ambiguous_gap: float = 0.08   # top1 与 top2 差距小于此值 → 视为不确定
    field_cache: dict = field(default_factory=dict)

    def route(self, query: str, industry_hint: Optional[str] = None) -> RouteResult:
        experts = list(self.registry.experts.values())

        # ---- L1 规则匹配 ----
        q = query.lower()
        l1 = []
        for e in experts:
            hits = sum(1 for k in e.keywords if k.lower() in q)
            if hits:
                l1.append((hits, e))
        l1.sort(key=lambda x: x[0], reverse=True)
        if l1 and l1[0][0] >= self.l1_min_hits and (len(l1) == 1 or l1[0][0] > l1[1][0]):
            chosen = [l1[0][1]]
            return self._finish(chosen, "L1", min(1.0, l1[0][0] / 4), query)

        # ---- L2 语义路由 ----
        if self.embed:
            qv = self.embed(query)
            scored = sorted(
                ((_cosine(qv, e.embedding), e) for e in experts if e.embedding),
                key=lambda x: x[0], reverse=True,
            )
            if scored and scored[0][0] >= self.l2_threshold:
                top = scored[0]
                gap = top[0] - (scored[1][0] if len(scored) > 1 else 0)
                if gap >= self.l2_ambiguous_gap:
                    return self._finish([top[1]], "L2", top[0], query)
                # 不确定 → 取并列 top（多专家并行），交给 L3 或直接合并
                candidates = [e for s, e in scored[:3] if s >= self.l2_threshold - 0.05]
                if self.llm_confirm:
                    eid = self.llm_confirm(query, candidates)
                    pick = self.registry.experts.get(eid, candidates[0])
                    return self._finish([pick], "L3", top[0], query)
                return self._finish(candidates[:2], "L2", top[0], query)  # 多 Skill 并行

        # ---- fallback：通用，无专家注入 ----
        return self._finish([], "fallback", 0.0, query)

    def _difficulty(self, query: str, experts: list[Expert]) -> str:
        # 难度分级（Kimi 渐进推理用）：长度 + 多专家 + 深度专家 → 提升难度档
        n = len(query)
        multi = len(experts) > 1
        deep = any(e.depth >= 3 for e in experts)
        score = (n > 120) + multi + deep + bool(re.search(r"计算|校核|对比|方案|为什么|如何", query))
        return "hard" if score >= 3 else "medium" if score >= 1 else "easy"

    def _finish(self, experts: list[Expert], level: str, conf: float, query: str) -> RouteResult:
        if experts:
            joined = "\n\n---\n\n".join(f"# 专家：{e.name}\n{e.system_prompt}" for e in experts)
            header = f"你现在以「{ '、'.join(e.name for e in experts) }」专家身份作答，只在该专业范围内给确定结论。"
        else:
            joined, header = "", "你是机电安装领域通用助手，按通用工程规范作答。"
        injected = f"{header}\n\n{joined}{ARTIFACT_PROTOCOL}"
        return RouteResult(
            experts=experts, level=level, confidence=conf,
            difficulty=self._difficulty(query, experts), injected_system=injected,
        )

    @staticmethod
    def route_key(result: RouteResult) -> str:
        """给语义缓存用的路由键：同路由才允许复用缓存。"""
        return "|".join(sorted(e.id for e in result.experts)) or "fallback"
