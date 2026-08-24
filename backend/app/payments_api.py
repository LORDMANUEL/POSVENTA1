from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .accounting_integration import AccountingIntegrationService
from .commerce_models import Order, OrderStatus, Payment, PaymentStatus
from .config import get_settings
from .db import get_db
from .models import User, UserRole
from .module_api import external_mode, require_enabled_module
from .payment_gateway import SandboxPaymentAdapter
from .security import require_roles
from .services import AuditService


payments_router = APIRouter(
    prefix="/payments",
    tags=["payments"],
    dependencies=[Depends(require_enabled_module("payments"))],
)


def _adapter() -> SandboxPaymentAdapter:
    settings = get_settings()
    return SandboxPaymentAdapter(settings.payment_sandbox_webhook_secret)


def _locked_order_and_payment(
    db: Session,
    tenant_id: str,
    order_id: str,
) -> tuple[Order, Payment]:
    order_query = select(Order).where(
        Order.id == order_id,
        Order.tenant_id == tenant_id,
    )
    if db.get_bind().dialect.name == "postgresql":
        order_query = order_query.with_for_update()
    order = db.scalar(order_query)
    if order is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    payment_query = (
        select(Payment)
        .where(Payment.order_id == order.id, Payment.tenant_id == tenant_id)
        .order_by(Payment.created_at.desc())
    )
    if db.get_bind().dialect.name == "postgresql":
        payment_query = payment_query.with_for_update()
    payment = db.scalar(payment_query)
    if payment is None:
        raise HTTPException(status_code=409, detail="Pedido sin registro de pago")
    return order, payment


@payments_router.get("/status")
def payment_status(
    _: User = Depends(
        require_roles(
            UserRole.OWNER,
            UserRole.ADMIN,
            UserRole.MANAGER,
            UserRole.AUDITOR,
        )
    ),
) -> dict:
    mode = external_mode("payments")
    provider = "sandbox" if mode == "sandbox" else "external"
    return {"provider": provider, "mode": mode}


@payments_router.post("/orders/{order_id}/intent", status_code=201)
def create_payment_intent(
    order_id: str,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=100),
    ],
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(
            UserRole.OWNER,
            UserRole.ADMIN,
            UserRole.MANAGER,
            UserRole.CASHIER,
            UserRole.SALES,
        )
    ),
) -> dict:
    mode = external_mode("payments")
    if mode != "sandbox":
        raise HTTPException(
            status_code=409,
            detail="El adaptador de pago real todavía no está configurado en esta instalación",
        )

    order, payment = _locked_order_and_payment(db, user.tenant_id, order_id)
    if payment.status not in {PaymentStatus.PENDING, PaymentStatus.FAILED}:
        raise HTTPException(status_code=409, detail="El pago ya no acepta una nueva intención")

    intent = _adapter().create_intent(
        tenant_id=user.tenant_id,
        order_id=order.id,
        amount=payment.amount,
        idempotency_key=idempotency_key,
    )
    if payment.external_reference and payment.external_reference != intent.reference:
        raise HTTPException(
            status_code=409,
            detail="El pedido ya tiene una intención de pago diferente",
        )
    payment.external_reference = intent.reference
    AuditService.record(
        db,
        user,
        "payment.intent.created",
        "payment",
        payment.id,
        {
            "provider": intent.provider,
            "provider_reference": intent.reference,
            "order_id": order.id,
            "amount": intent.amount,
        },
    )
    db.commit()
    return {
        "provider": intent.provider,
        "reference": intent.reference,
        "status": intent.status,
        "amount": intent.amount,
    }


@payments_router.post("/orders/{order_id}/sandbox-confirm")
def confirm_sandbox_payment(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)
    ),
) -> dict:
    if external_mode("payments") != "sandbox":
        raise HTTPException(status_code=404, detail="Confirmación sandbox no disponible")

    order, payment = _locked_order_and_payment(db, user.tenant_id, order_id)
    if not payment.external_reference or not payment.external_reference.startswith("mz_sandbox_"):
        raise HTTPException(status_code=409, detail="No existe una intención sandbox para este pedido")
    if payment.status == PaymentStatus.PAID:
        return {
            "payment_id": payment.id,
            "payment_status": payment.status.value,
            "order_status": order.status.value,
            "reference": payment.external_reference,
        }
    if payment.status not in {PaymentStatus.PENDING, PaymentStatus.FAILED}:
        raise HTTPException(status_code=409, detail="El pago no está en estado confirmable")

    payment.status = PaymentStatus.PAID
    if order.status == OrderStatus.PENDING_PAYMENT:
        order.status = OrderStatus.CONFIRMED
    AccountingIntegrationService.post_order_revenue(db, user, order, payment.method)
    AuditService.record(
        db,
        user,
        "payment.sandbox.confirmed",
        "payment",
        payment.id,
        {
            "order_id": order.id,
            "provider_reference": payment.external_reference,
        },
    )
    db.commit()
    return {
        "payment_id": payment.id,
        "payment_status": payment.status.value,
        "order_status": order.status.value,
        "reference": payment.external_reference,
    }
