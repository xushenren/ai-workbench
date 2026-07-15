"""kb_api.py — 知识库三池 REST 接口"""
from __future__ import annotations
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from org_core import SqliteRepos as OrgRepo
from kb_core import KBService, SqliteKBRepo

router = APIRouter(prefix="/v1/kb")
_org_repo = OrgRepo(os.getenv("ORG_DB", "/data/org_core.db"))
_kb_repo = SqliteKBRepo(os.getenv("KB_DB", "/data/kb_core.db"))
kb = KBService(_org_repo, _kb_repo, model_inspector=None)


# --- schemas ---
class UploadIn(BaseModel):
    tenant_id: str
    grant_id: str
    title: str
    content: str
    share: bool = False

class PromoteIn(BaseModel):
    tenant_id: str
    grant_id: str
    title: str
    content: str = ""
    claims: dict = {}
    decision_override: bool = False

class RollbackIn(BaseModel):
    tenant_id: str
    grant_id: str
    entry_id: str

class RetrieveIn(BaseModel):
    tenant_id: str
    grant_id: str | None = None
    query: str


# --- routes ---
@router.post("/upload")
def upload(body: UploadIn):
    entry = kb.upload(body.tenant_id, body.grant_id,
                      title=body.title, content=body.content, share=body.share)
    return entry.__dict__

@router.post("/promote")
def promote(body: PromoteIn):
    entry, report = kb.promote_to_high(body.tenant_id, body.grant_id,
                                        title=body.title, content=body.content,
                                        claims=body.claims,
                                        decision_override=body.decision_override)
    return {"entry": entry.__dict__, "inspection": report.__dict__ if report else None}

@router.post("/rollback")
def rollback(body: RollbackIn):
    kb.rollback(body.tenant_id, body.grant_id, body.entry_id)
    return {"status": "rolled_back"}

@router.post("/retrieve")
def retrieve(body: RetrieveIn):
    hits = kb.retrieve(body.tenant_id, body.grant_id, body.query)
    return [h.__dict__ for h in hits]

@router.get("/entries/{tenant_id}/{grant_id}")
def list_entries(tenant_id: str, grant_id: str):
    hits = kb.retrieve(tenant_id, grant_id, "")
    return [h.__dict__ for h in hits]
