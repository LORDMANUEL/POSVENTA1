import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .fiscal_models import FiscalDocument, FiscalRange
from .models import Branch, User, UserRole
from .module_api import require_enabled_module
from .security import require_roles
from .services import AuditService

fiscal_router = APIRouter(prefix="/fiscal", tags=["fiscal"], dependencies=[Depends(require_enabled_module("fiscal"))])


class FiscalRangeIn(BaseModel):
    branch_id: str
    document_type: str = Field(min_length=2, max_length=40)
    cai: str = Field(min_length=2, max_length=80)
    prefix: str = Field(min_length=1, max_length=40)
    range_start: int = Field(ge=0)
    range_end: int = Field(ge=0)
    expires_on: date | None = None


class FiscalIssueIn(BaseModel):
    branch_id: str
    document_type: str = Field(min_length=2, max_length=40)
    source_type: str = Field(min_length=2, max_length=40)
    source_id: str = Field(min_length=1, max_length=64)
    payload: dict = Field(default_factory=dict)


class FiscalVoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


@fiscal_router.get("/ranges")
def list_ranges(db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.AUDITOR))) -> list[dict]:
    rows = db.scalars(select(FiscalRange).where(FiscalRange.tenant_id == user.tenant_id).order_by(FiscalRange.created_at.desc())).all()
    return [{"id": r.id, "branch_id": r.branch_id, "document_type": r.document_type, "cai": r.cai, "prefix": r.prefix, "range_start": r.range_start, "range_end": r.range_end, "current_number": r.current_number, "expires_on": r.expires_on, "active": r.active} for r in rows]


@fiscal_router.post("/ranges", status_code=201)
def create_range(payload: FiscalRangeIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN))) -> dict:
    if payload.range_end < payload.range_start:
        raise HTTPException(status_code=422, detail="El fin del rango no puede ser menor al inicio")
    if not db.scalar(select(Branch.id).where(Branch.id == payload.branch_id, Branch.tenant_id == user.tenant_id)):
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    row = FiscalRange(tenant_id=user.tenant_id, current_number=payload.range_start - 1, **payload.model_dump())
    db.add(row)
    db.flush()
    AuditService.record(db, user, "fiscal.range.created", "fiscal_range", row.id, {"document_type": row.document_type, "cai": row.cai})
    db.commit()
    return {"id": row.id, "current_number": row.current_number, "active": row.active}


@fiscal_router.post("/documents", status_code=201)
def issue_document(payload: FiscalIssueIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.CASHIER))) -> dict:
    existing = db.scalar(select(FiscalDocument).where(FiscalDocument.tenant_id == user.tenant_id, FiscalDocument.source_type == payload.source_type, FiscalDocument.source_id == payload.source_id))
    if existing:
        return {"id": existing.id, "document_number": existing.document_number, "status": existing.status, "cai": existing.cai}

    query = select(FiscalRange).where(FiscalRange.tenant_id == user.tenant_id, FiscalRange.branch_id == payload.branch_id, FiscalRange.document_type == payload.document_type, FiscalRange.active.is_(True)).order_by(FiscalRange.created_at.desc())
    # PostgreSQL serializes concurrent issuance on the selected range. SQLite tests safely ignore FOR UPDATE.
    if db.bind and db.bind.dialect.name != "sqlite":
        query = query.with_for_update()
    fiscal_range = db.scalar(query)
    if not fiscal_range:
        raise HTTPException(status_code=409, detail="No hay rango fiscal activo para este documento y sucursal")
    if fiscal_range.expires_on and fiscal_range.expires_on < date.today():
        raise HTTPException(status_code=409, detail="El rango fiscal está vencido")
    next_number = fiscal_range.current_number + 1
    if next_number > fiscal_range.range_end:
        raise HTTPException(status_code=409, detail="El rango fiscal está agotado")
    fiscal_range.current_number = next_number
    document_number = f"{fiscal_range.prefix}{next_number:08d}"
    row = FiscalDocument(tenant_id=user.tenant_id, branch_id=payload.branch_id, fiscal_range_id=fiscal_range.id, document_type=payload.document_type, document_number=document_number, cai=fiscal_range.cai, source_type=payload.source_type, source_id=payload.source_id, payload_json=json.dumps(payload.payload, ensure_ascii=False), issued_by_user_id=user.id)
    db.add(row)
    db.flush()
    AuditService.record(db, user, "fiscal.document.issued", "fiscal_document", row.id, {"number": row.document_number, "source_type": row.source_type, "source_id": row.source_id})
    db.commit()
    return {"id": row.id, "document_number": row.document_number, "status": row.status, "cai": row.cai}


@fiscal_router.post("/documents/{document_id}/void")
def void_document(document_id: str, payload: FiscalVoidIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER))) -> dict:
    row = db.scalar(select(FiscalDocument).where(FiscalDocument.id == document_id, FiscalDocument.tenant_id == user.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Documento fiscal no encontrado")
    if row.status == "voided":
        return {"id": row.id, "status": row.status, "voided_at": row.voided_at}
    row.status = "voided"
    row.void_reason = payload.reason
    row.voided_at = datetime.now(timezone.utc)
    AuditService.record(db, user, "fiscal.document.voided", "fiscal_document", row.id, {"reason": payload.reason})
    db.commit()
    return {"id": row.id, "status": row.status, "voided_at": row.voided_at}
