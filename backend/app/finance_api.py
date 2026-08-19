from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .finance_models import BankAccount, BankTransaction, Payable, PayablePayment, Receivable, ReceivablePayment
from .models import User, UserRole
from .module_api import require_enabled_module
from .ops_models import Customer, Supplier
from .security import require_roles
from .services import AuditService

receivables_router = APIRouter(prefix="/finance/receivables", tags=["receivables"], dependencies=[Depends(require_enabled_module("receivables"))])
payables_router = APIRouter(prefix="/finance/payables", tags=["payables"], dependencies=[Depends(require_enabled_module("payables"))])
banking_router = APIRouter(prefix="/finance/banking", tags=["banking"], dependencies=[Depends(require_enabled_module("banking"))])


class OpenItemIn(BaseModel):
    party_id: str
    reference: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=2000)
    amount: Decimal = Field(gt=0)
    due_date: date | None = None


class PaymentIn(BaseModel):
    amount: Decimal = Field(gt=0)
    method: str = Field(min_length=2, max_length=40)
    reference: str | None = Field(default=None, max_length=120)


class BankAccountIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    bank_name: str = Field(min_length=2, max_length=160)
    currency: str = Field(default="HNL", min_length=3, max_length=3)
    account_last4: str | None = Field(default=None, min_length=4, max_length=4)
    ledger_account_id: str | None = None


class BankTransactionIn(BaseModel):
    transaction_date: date
    description: str = Field(default="", max_length=2000)
    amount: Decimal
    external_reference: str = Field(min_length=1, max_length=160)


def apply_payment(balance: Decimal, amount: Decimal) -> tuple[Decimal, str]:
    if amount > balance:
        raise HTTPException(status_code=409, detail="El pago excede el saldo pendiente")
    new_balance = (balance - amount).quantize(Decimal("0.01"))
    return new_balance, "paid" if new_balance == 0 else "partial"


@receivables_router.get("")
def list_receivables(db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.AUDITOR))) -> list[dict]:
    rows = db.scalars(select(Receivable).where(Receivable.tenant_id == user.tenant_id).order_by(Receivable.created_at.desc())).all()
    return [{"id": r.id, "customer_id": r.customer_id, "reference": r.reference, "original_amount": str(r.original_amount), "balance": str(r.balance), "due_date": r.due_date, "status": r.status} for r in rows]


@receivables_router.post("", status_code=201)
def create_receivable(payload: OpenItemIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER))) -> dict:
    if not db.scalar(select(Customer.id).where(Customer.id == payload.party_id, Customer.tenant_id == user.tenant_id)):
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if db.scalar(select(Receivable.id).where(Receivable.tenant_id == user.tenant_id, Receivable.reference == payload.reference)):
        raise HTTPException(status_code=409, detail="Referencia por cobrar ya registrada")
    row = Receivable(tenant_id=user.tenant_id, customer_id=payload.party_id, reference=payload.reference, description=payload.description, original_amount=payload.amount, balance=payload.amount, due_date=payload.due_date)
    db.add(row)
    db.flush()
    AuditService.record(db, user, "receivable.created", "receivable", row.id, {"reference": row.reference, "amount": str(row.original_amount)})
    db.commit()
    return {"id": row.id, "reference": row.reference, "balance": str(row.balance), "status": row.status}


@receivables_router.post("/{receivable_id}/payments", status_code=201)
def receive_payment(receivable_id: str, payload: PaymentIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.CASHIER))) -> dict:
    item = db.scalar(select(Receivable).where(Receivable.id == receivable_id, Receivable.tenant_id == user.tenant_id))
    if not item:
        raise HTTPException(status_code=404, detail="Cuenta por cobrar no encontrada")
    new_balance, status = apply_payment(Decimal(item.balance), payload.amount)
    payment = ReceivablePayment(tenant_id=user.tenant_id, receivable_id=item.id, amount=payload.amount, method=payload.method, reference=payload.reference, received_by_user_id=user.id)
    db.add(payment)
    item.balance = new_balance
    item.status = status
    AuditService.record(db, user, "receivable.paid", "receivable", item.id, {"amount": str(payload.amount), "balance": str(new_balance)})
    db.commit()
    return {"id": payment.id, "receivable_id": item.id, "balance": str(item.balance), "status": item.status}


@payables_router.get("")
def list_payables(db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.AUDITOR))) -> list[dict]:
    rows = db.scalars(select(Payable).where(Payable.tenant_id == user.tenant_id).order_by(Payable.created_at.desc())).all()
    return [{"id": r.id, "supplier_id": r.supplier_id, "reference": r.reference, "original_amount": str(r.original_amount), "balance": str(r.balance), "due_date": r.due_date, "status": r.status} for r in rows]


@payables_router.post("", status_code=201)
def create_payable(payload: OpenItemIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER))) -> dict:
    if not db.scalar(select(Supplier.id).where(Supplier.id == payload.party_id, Supplier.tenant_id == user.tenant_id)):
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    if db.scalar(select(Payable.id).where(Payable.tenant_id == user.tenant_id, Payable.reference == payload.reference)):
        raise HTTPException(status_code=409, detail="Referencia por pagar ya registrada")
    row = Payable(tenant_id=user.tenant_id, supplier_id=payload.party_id, reference=payload.reference, description=payload.description, original_amount=payload.amount, balance=payload.amount, due_date=payload.due_date)
    db.add(row)
    db.flush()
    AuditService.record(db, user, "payable.created", "payable", row.id, {"reference": row.reference, "amount": str(row.original_amount)})
    db.commit()
    return {"id": row.id, "reference": row.reference, "balance": str(row.balance), "status": row.status}


@payables_router.post("/{payable_id}/payments", status_code=201)
def pay_payable(payable_id: str, payload: PaymentIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER))) -> dict:
    item = db.scalar(select(Payable).where(Payable.id == payable_id, Payable.tenant_id == user.tenant_id))
    if not item:
        raise HTTPException(status_code=404, detail="Cuenta por pagar no encontrada")
    new_balance, status = apply_payment(Decimal(item.balance), payload.amount)
    payment = PayablePayment(tenant_id=user.tenant_id, payable_id=item.id, amount=payload.amount, method=payload.method, reference=payload.reference, paid_by_user_id=user.id)
    db.add(payment)
    item.balance = new_balance
    item.status = status
    AuditService.record(db, user, "payable.paid", "payable", item.id, {"amount": str(payload.amount), "balance": str(new_balance)})
    db.commit()
    return {"id": payment.id, "payable_id": item.id, "balance": str(item.balance), "status": item.status}


@banking_router.get("/accounts")
def list_bank_accounts(db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.AUDITOR))) -> list[dict]:
    rows = db.scalars(select(BankAccount).where(BankAccount.tenant_id == user.tenant_id).order_by(BankAccount.name)).all()
    return [{"id": row.id, "name": row.name, "bank_name": row.bank_name, "currency": row.currency, "account_last4": row.account_last4, "ledger_account_id": row.ledger_account_id} for row in rows]


@banking_router.post("/accounts", status_code=201)
def create_bank_account(payload: BankAccountIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN))) -> dict:
    row = BankAccount(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(row)
    db.flush()
    AuditService.record(db, user, "bank_account.created", "bank_account", row.id, {"name": row.name})
    db.commit()
    return {"id": row.id, "name": row.name, "bank_name": row.bank_name, "currency": row.currency}


@banking_router.post("/accounts/{bank_account_id}/transactions", status_code=201)
def add_bank_transaction(bank_account_id: str, payload: BankTransactionIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER))) -> dict:
    account = db.scalar(select(BankAccount).where(BankAccount.id == bank_account_id, BankAccount.tenant_id == user.tenant_id))
    if not account:
        raise HTTPException(status_code=404, detail="Cuenta bancaria no encontrada")
    duplicate = db.scalar(select(BankTransaction.id).where(BankTransaction.tenant_id == user.tenant_id, BankTransaction.bank_account_id == account.id, BankTransaction.external_reference == payload.external_reference))
    if duplicate:
        raise HTTPException(status_code=409, detail="Movimiento bancario duplicado")
    tx = BankTransaction(tenant_id=user.tenant_id, bank_account_id=account.id, **payload.model_dump())
    db.add(tx)
    db.flush()
    AuditService.record(db, user, "bank_transaction.imported", "bank_transaction", tx.id, {"reference": tx.external_reference, "amount": str(tx.amount)})
    db.commit()
    return {"id": tx.id, "amount": str(tx.amount), "reconciliation_status": tx.reconciliation_status}
