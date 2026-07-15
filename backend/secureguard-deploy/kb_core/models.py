"""
kb_core.models — 知识库三池 + 置信度 的领域模型。

三池:私有 / 公有低置信 / 公有高置信。
每条知识带 claims(可判定的事实声明,键→值),用于 claim 级一致性体检
(替代不可靠的 embedding 余弦)。external_ok 标记"对外可公开"(独立于内部 public)。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Pool(str, Enum):
    PRIVATE = "private"          # 仅 owner 本人
    PUBLIC_LOW = "public_low"    # 用户同意共享 → 公有但低置信
    PUBLIC_HIGH = "public_high"  # 专家拍板入库 → 公有高置信


class EntryStatus(str, Enum):
    ACTIVE = "active"
    ROLLED_BACK = "rolled_back"  # 晋升出错,一键退回/作废


@dataclass
class KBEntry:
    id: str
    tenant_id: str
    pool: Pool
    owner_user_id: str           # 真人
    owner_grant_id: str          # 上传时的子账号
    org_node_id: str             # 来源组织节点(范围)
    title: str
    content: str
    claims: dict[str, str] = field(default_factory=dict)  # 事实声明:键→值,用于体检
    shared: bool = False         # 用户是否同意共享(决定可见性,不决定置信)
    external_ok: bool = False    # 对外可公开(供匿名 bot;独立于内部 public)
    source: str = ""             # 来源说明
    status: EntryStatus = EntryStatus.ACTIVE
    ai_verdict: str = ""         # AI 体检结论(留痕)
    promoted_by: Optional[str] = None   # 拍板专家 user_id
    created_at: float = field(default_factory=time.time)


@dataclass
class Inspection:
    """AI 体检报告(副手,不裁决)。"""
    conflicts: list[str] = field(default_factory=list)    # 与高置信池冲突的点
    anomalies: list[str] = field(default_factory=list)    # 异常/垃圾/注入嫌疑
    confidence_advice: str = "ok"                          # 给专家的建议
    @property
    def has_conflict(self) -> bool:
        return bool(self.conflicts)
