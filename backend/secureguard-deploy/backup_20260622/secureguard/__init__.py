"""secureguard — 企业垂类模型五层安全门控系统。

层次：
    L0 InputGuard       输入守卫（陷阱检测 + sanitize + instruction sandwich）
    L1 gate/arbitrate   仲裁门控（12 红线 + 6 领域护栏 + 自省 + 冲突裁决）
    L2 RAGPipeline      推理 + 检索增强（离线 Mock / 生产 vLLM+Chroma 适配）
    L3 OutputGuard      输出守卫（幻觉信号 + 12+ 凭据脱敏 + 质量评分）
    L4 AuditLogger      审计（哈希化、不存原文、冲突可见）
    Orchestrator        协调器，异步串联五层
"""
from .types import Token, GateResult, Rule, Conflict, TrapResult, LADDER
from .l0_input_guard import InputGuard
from .l1_gate import gate, arbitrate, self_monitor, load_domain_guard, REDLINES
from .l2_reasoning import (
    Doc, ModelBackend, VectorStore, MockModel, InMemoryVectorStore,
    RAGPipeline, StepwiseReasoner, VLLMModel, ChromaVectorStore,
)
from .l3_output_guard import OutputGuard, OutputQuality
from .l4_audit import AuditLogger, AuditEntry
from .audit_rotation import RotatingAuditLogger
from .retrieval_guard import RetrievalGuard, RetrievalReport, RetrievalViolation
from .evolution_gates import EvolutionGates, Patch, GateOutcome
from .safety_proxy import SafetyProxy, ProxyConfig
from .compute_router import (
    ComputeRouter, DataClassifier, DataClass, Tier, TierStatus, RouteDecision, AgentComputePolicy,
)
from .trace import TraceFrame, build_public_trace, build_audit_trace, split_frame
from .permissions import (
    Role, Visibility, AgentStatus, PermissionDenied, User as RBACUser, Agent as RBACAgent,
    KnowledgeBase, can_create_agent, create_agent, submit_for_review, approve, reject,
    can_use_agent, can_access_kb, can_read_kb_content, can_manage_kb, can_manage_quota,
)
from .output_contract import OutputContract, ContractResult, REQUIRED_SECTIONS
from .orchestrator import Orchestrator

__version__ = "1.5.0"

__all__ = [
    "Token", "GateResult", "Rule", "Conflict", "TrapResult", "LADDER",
    "InputGuard",
    "gate", "arbitrate", "self_monitor", "load_domain_guard", "REDLINES",
    "Doc", "ModelBackend", "VectorStore", "MockModel", "InMemoryVectorStore",
    "RAGPipeline", "StepwiseReasoner", "VLLMModel", "ChromaVectorStore",
    "OutputGuard", "OutputQuality",
    "AuditLogger", "AuditEntry", "RotatingAuditLogger",
    "RetrievalGuard", "RetrievalReport", "RetrievalViolation",
    "EvolutionGates", "Patch", "GateOutcome",
    "SafetyProxy", "ProxyConfig",
    "ComputeRouter", "DataClassifier", "DataClass", "Tier", "TierStatus", "RouteDecision",
    "AgentComputePolicy",
    "TraceFrame", "build_public_trace", "build_audit_trace", "split_frame",
    "Role", "Visibility", "AgentStatus", "PermissionDenied", "RBACUser", "RBACAgent",
    "KnowledgeBase", "can_create_agent", "create_agent", "submit_for_review", "approve",
    "reject", "can_use_agent", "can_access_kb", "can_read_kb_content", "can_manage_kb",
    "can_manage_quota",
    "OutputContract", "ContractResult", "REQUIRED_SECTIONS",
    "Orchestrator",
]
