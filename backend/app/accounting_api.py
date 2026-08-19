from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .accounting_models import Account, JournalEntry, JournalLine
from .db import get_db
from .models import User, UserRole
from .security import require_roles
from .services import AuditService

accounting_router = APIRouter(prefix="/accounting", tags=["accounting"])


class AccountIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=2, max_length=180)
    account_type: str = Field(pattern="^(asset|liability|equity|income|expense)$")
    parent_id: str | None = None


class JournalLineIn(BaseModel):
    account_id: str
    branch_id: str | None = None
    memo: str = Field(default="", max_length=255)
    debit: Decimal = Field(default=Decimal("0"), ge=0)
    credit: Decimal = Field(default=Decimal("0"), ge=0)


class JournalEntryIn(BaseModel):
    reference: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=2000)
    source_type: str | None = Field(default=None, max_length=60)
    source_id: str | None = Field(default=None, max_length=64)
    lines: list[JournalLineIn]


def validate_lines(lines: list[JournalLineIn]) -> tuple[Decimal, Decimal]:
    if len(lines) < 2:
        raise HTTPException(status_code=422, detail="Un asiento requiere al menos dos líneas")
    debit = sum((line.debit for line in lines), Decimal("0"))
    credit = sum((line.credit for line in lines), Decimal("0"))
    for line in lines:
        if (line.debit > 0 and line.credit > 0) or (line.debit == 0 and line.credit == 0):
            raise HTTPException(status_code=422, detail="Cada línea debe tener débito o crédito, no ambos")
    if debit.quantize(Decimal("0.01")) != credit.quantize(Decimal("0.01")):
        raise HTTPException(status_code=422, detail="El asiento no está balanceado")
    return debit, credit


@accounting_router.get("/accounts")
def list_accounts(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.AUDITOR)),
) -> list[dict]:
    rows = db.scalars(select(Account).where(Account.tenant_id == user.tenant_id).order_by(Account.code)).all()
    return [
        {"id": row.id, "code": row.code, "name": row.name, "account_type": row.account_type,
         "parent_id": row.parent_id, "active": row.active, "system": row.system}
        for row in rows
    ]


@accounting_router.post("/accounts", status_code=201)
def create_account(
    payload: AccountIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    if db.scalar(select(Account.id).where(Account.tenant_id == user.tenant_id, Account.code == payload.code)):
        raise HTTPException(status_code=409, detail="Código de cuenta ya registrado")
    if payload.parent_id and not db.scalar(
        select(Account.id).where(Account.id == payload.parent_id, Account.tenant_id == user.tenant_id)
    ):
        raise HTTPException(status_code=404, detail="Cuenta padre no encontrada")
    row = Account(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(row)
    db.flush()
    AuditService.record(db, user, "account.created", "account", row.id, {"code": row.code})
    db.commit()
    return {"id": row.id, "code": row.code, "name": row.name, "account_type": row.account_type}


@accounting_router.post("/entries", status_code=201)
def create_entry(
    payload: JournalEntryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict:
    validate_lines(payload.lines)
    if db.scalar(
        select(JournalEntry.id).where(
            JournalEntry.tenant_id == user.tenant_id,
            JournalEntry.reference == payload.reference,
        )
    ):
        raise HTTPException(status_code=409, detail="Referencia contable ya registrada")

    account_ids = {line.account_id for line in payload.lines}
    existing = set(db.scalars(
        select(Account.id).where(Account.tenant_id == user.tenant_id, Account.id.in_(account_ids), Account.active.is_(True))
    ).all())
    if existing != account_ids:
        raise HTTPException(status_code=422, detail="Una o más cuentas no existen o están inactivas")

    entry = JournalEntry(
        tenant_id=user.tenant_id,
        reference=payload.reference,
        description=payload.description,
        source_type=payload.source_type,
        source_id=payload.source_id,
    )
    db.add(entry)
    db.flush()
    for line in payload.lines:
        db.add(JournalLine(journal_entry_id=entry.id, **line.model_dump()))
    AuditService.record(db, user, "journal.created", "journal_entry", entry.id, {"reference": entry.reference})
    db.commit()
    return {"id": entry.id, "reference": entry.reference, "status": entry.status}


@accounting_router.post("/entries/{entry_id}/post")
def post_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict:
    entry = db.scalar(select(JournalEntry).where(JournalEntry.id == entry_id, JournalEntry.tenant_id == user.tenant_id))
    if not entry:
        raise HTTPException(status_code=404, detail="Asiento no encontrado")
    if entry.status == "posted":
        return {"id": entry.id, "status": entry.status, "posted_at": entry.posted_at}
    lines = db.scalars(select(JournalLine).where(JournalLine.journal_entry_id == entry.id)).all()
    debit = sum((Decimal(line.debit) for line in lines), Decimal("0"))
    credit = sum((Decimal(line.credit) for line in lines), Decimal("0"))
    if debit.quantize(Decimal("0.01")) != credit.quantize(Decimal("0.01")):
        raise HTTPException(status_code=409, detail="El asiento dejó de estar balanceado")
    entry.status = "posted"
    entry.posted_at = datetime.now(timezone.utc)
    entry.posted_by_user_id = user.id
    AuditService.record(db, user, "journal.posted", "journal_entry", entry.id, {"reference": entry.reference})
    db.commit()
    return {"id": entry.id, "status": entry.status, "posted_at": entry.posted_at}


@accounting_router.get("/trial-balance")
def trial_balance(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.AUDITOR)),
) -> list[dict]:
    rows = db.execute(
        select(
            Account.id,
            Account.code,
            Account.name,
            Account.account_type,
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(JournalLine, JournalLine.account_id == Account.id, isouter=True)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id, isouter=True)
        .where(Account.tenant_id == user.tenant_id)
        .where((JournalEntry.status == "posted") | (JournalEntry.id.is_(None)))
        .group_by(Account.id, Account.code, Account.name, Account.account_type)
        .order_by(Account.code)
    ).all()
    return [
        {
            "account_id": row[0], "code": row[1], "name": row[2], "account_type": row[3],
            "debit": str(row[4]), "credit": str(row[5]), "balance": str(Decimal(row[4]) - Decimal(row[5])),
        }
        for row in rows
    ]
