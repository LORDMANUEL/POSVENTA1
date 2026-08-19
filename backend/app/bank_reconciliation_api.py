from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import get_db
from .finance_models import BankTransaction, PayablePayment, ReceivablePayment
from .models import User, UserRole
from .module_api import require_enabled_module
from .security import require_roles
from .services import AuditService

reconciliation_router = APIRouter(
    prefix="/finance/reconciliation",
    tags=["bank-reconciliation"],
    dependencies=[Depends(require_enabled_module("banking"))],
)


class MatchIn(BaseModel):
    matched_type: str = Field(pattern="^(receivable_payment|payable_payment)$")
    matched_id: str


def _candidate(db: Session, tenant_id: str, matched_type: str, matched_id: str):
    model = ReceivablePayment if matched_type == "receivable_payment" else PayablePayment
    row = db.scalar(
        select(model).where(model.id == matched_id, model.tenant_id == tenant_id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Movimiento interno no encontrado")
    return row


@reconciliation_router.get("/unmatched")
def list_unmatched(
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.AUDITOR)
    ),
) -> list[dict]:
    rows = db.scalars(
        select(BankTransaction)
        .where(
            BankTransaction.tenant_id == user.tenant_id,
            BankTransaction.reconciliation_status == "unmatched",
        )
        .order_by(
            BankTransaction.transaction_date.desc(),
            BankTransaction.created_at.desc(),
        )
    ).all()
    return [
        {
            "id": row.id,
            "bank_account_id": row.bank_account_id,
            "transaction_date": row.transaction_date,
            "description": row.description,
            "amount": str(row.amount),
            "external_reference": row.external_reference,
            "status": row.reconciliation_status,
        }
        for row in rows
    ]


@reconciliation_router.get("/{bank_transaction_id}/suggestions")
def suggestions(
    bank_transaction_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.AUDITOR)
    ),
) -> list[dict]:
    tx = db.scalar(
        select(BankTransaction).where(
            BankTransaction.id == bank_transaction_id,
            BankTransaction.tenant_id == user.tenant_id,
        )
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Movimiento bancario no encontrado")
    amount = Decimal(tx.amount)
    results: list[dict] = []
    if amount > 0:
        rows = db.scalars(
            select(ReceivablePayment)
            .where(
                ReceivablePayment.tenant_id == user.tenant_id,
                ReceivablePayment.amount == amount,
            )
            .order_by(ReceivablePayment.paid_at.desc())
            .limit(20)
        ).all()
        results.extend(
            {
                "matched_type": "receivable_payment",
                "matched_id": row.id,
                "amount": str(row.amount),
                "reference": row.reference,
                "paid_at": row.paid_at,
                "score_reason": "mismo_monto_entrada",
            }
            for row in rows
        )
    elif amount < 0:
        target = -amount
        rows = db.scalars(
            select(PayablePayment)
            .where(
                PayablePayment.tenant_id == user.tenant_id,
                PayablePayment.amount == target,
            )
            .order_by(PayablePayment.paid_at.desc())
            .limit(20)
        ).all()
        results.extend(
            {
                "matched_type": "payable_payment",
                "matched_id": row.id,
                "amount": str(row.amount),
                "reference": row.reference,
                "paid_at": row.paid_at,
                "score_reason": "mismo_monto_salida",
            }
            for row in rows
        )
    return results


@reconciliation_router.post("/{bank_transaction_id}/match")
def match_transaction(
    bank_transaction_id: str,
    payload: MatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict:
    tx = db.scalar(
        select(BankTransaction)
        .where(
            BankTransaction.id == bank_transaction_id,
            BankTransaction.tenant_id == user.tenant_id,
        )
        .with_for_update()
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Movimiento bancario no encontrado")
    if tx.reconciliation_status == "matched":
        if tx.matched_type == payload.matched_type and tx.matched_id == payload.matched_id:
            return {
                "id": tx.id,
                "status": tx.reconciliation_status,
                "matched_type": tx.matched_type,
                "matched_id": tx.matched_id,
            }
        raise HTTPException(
            status_code=409,
            detail="El movimiento ya está conciliado con otra operación",
        )

    candidate = _candidate(db, user.tenant_id, payload.matched_type, payload.matched_id)
    bank_amount = Decimal(tx.amount)
    internal_amount = Decimal(candidate.amount)
    expected = internal_amount if payload.matched_type == "receivable_payment" else -internal_amount
    if bank_amount != expected:
        raise HTTPException(
            status_code=409,
            detail=f"Monto incompatible: banco={bank_amount} interno={expected}",
        )

    already = db.scalar(
        select(BankTransaction.id).where(
            BankTransaction.tenant_id == user.tenant_id,
            BankTransaction.reconciliation_status == "matched",
            BankTransaction.matched_type == payload.matched_type,
            BankTransaction.matched_id == payload.matched_id,
            BankTransaction.id != tx.id,
        )
    )
    if already:
        raise HTTPException(status_code=409, detail="La operación interna ya fue conciliada")

    tx.reconciliation_status = "matched"
    tx.matched_type = payload.matched_type
    tx.matched_id = payload.matched_id
    AuditService.record(
        db,
        user,
        "bank_transaction.matched",
        "bank_transaction",
        tx.id,
        {"matched_type": payload.matched_type, "matched_id": payload.matched_id},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="La operación interna ya fue conciliada por otra transacción",
        ) from exc
    return {
        "id": tx.id,
        "status": tx.reconciliation_status,
        "matched_type": tx.matched_type,
        "matched_id": tx.matched_id,
    }


@reconciliation_router.post("/{bank_transaction_id}/unmatch")
def unmatch_transaction(
    bank_transaction_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    tx = db.scalar(
        select(BankTransaction)
        .where(
            BankTransaction.id == bank_transaction_id,
            BankTransaction.tenant_id == user.tenant_id,
        )
        .with_for_update()
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Movimiento bancario no encontrado")
    previous = {"matched_type": tx.matched_type, "matched_id": tx.matched_id}
    tx.reconciliation_status = "unmatched"
    tx.matched_type = None
    tx.matched_id = None
    AuditService.record(
        db,
        user,
        "bank_transaction.unmatched",
        "bank_transaction",
        tx.id,
        previous,
    )
    db.commit()
    return {"id": tx.id, "status": tx.reconciliation_status}
