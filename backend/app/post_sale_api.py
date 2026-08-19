import json
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .cash_models import CashMovement
from .db import get_db
from .integrity import canonical_request_hash, require_idempotency_match
from .models import CashSession, PrintJob, Product, Sale, SaleLine, User, UserRole
from .module_api import require_enabled_module
from .post_sale_models import Refund, RefundStatus, ReturnLine, ReturnRecord
from .security import require_roles
from .services import AuditService, InventoryService, money

post_sale_router = APIRouter(
    prefix="/post-sales",
    tags=["post-sales"],
    dependencies=[Depends(require_enabled_module("returns"))],
)
POST_SALE_READ_ROLES = (
    UserRole.OWNER,
    UserRole.ADMIN,
    UserRole.MANAGER,
    UserRole.CASHIER,
    UserRole.AUDITOR,
)
POST_SALE_WRITE_ROLES = (
    UserRole.OWNER,
    UserRole.ADMIN,
    UserRole.MANAGER,
    UserRole.CASHIER,
)


class ReturnLineIn(BaseModel):
    sale_line_id: str
    quantity: Decimal = Field(gt=0)


class ReturnIn(BaseModel):
    sale_id: str
    reason: str = Field(min_length=3, max_length=240)
    lines: list[ReturnLineIn] = Field(min_length=1)


def quantity_text(value: Decimal) -> str:
    return format(Decimal(value).quantize(Decimal("0.001")), ".3f")


def already_returned_quantity(db: Session, sale_line_id: str) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(ReturnLine.quantity), 0)).where(
            ReturnLine.sale_line_id == sale_line_id
        )
    )
    return Decimal(value or 0)


def _return_hash(payload: ReturnIn) -> str:
    lines = [
        {"sale_line_id": line.sale_line_id, "quantity": line.quantity}
        for line in payload.lines
    ]
    lines.sort(key=lambda item: item["sale_line_id"])
    return canonical_request_hash(
        {"sale_id": payload.sale_id, "reason": payload.reason, "lines": lines}
    )


def sale_detail(db: Session, sale: Sale) -> dict:
    rows = db.execute(
        select(SaleLine, Product)
        .join(Product, Product.id == SaleLine.product_id)
        .where(SaleLine.sale_id == sale.id)
        .order_by(Product.name, SaleLine.id)
    ).all()
    lines = []
    for line, product in rows:
        returned = already_returned_quantity(db, line.id)
        returnable = max(Decimal("0"), Decimal(line.quantity) - returned)
        lines.append(
            {
                "sale_line_id": line.id,
                "product_id": line.product_id,
                "sku": product.sku,
                "name": product.name,
                "quantity_sold": quantity_text(line.quantity),
                "quantity_returned": quantity_text(returned),
                "quantity_returnable": quantity_text(returnable),
                "unit_price": str(line.unit_price),
                "line_total": str(line.line_total),
            }
        )
    return {
        "id": sale.id,
        "branch_id": sale.branch_id,
        "cashier_user_id": sale.cashier_user_id,
        "subtotal": str(sale.subtotal),
        "discount_total": str(sale.discount_total),
        "tax_total": str(sale.tax_total),
        "total": str(sale.total),
        "payment_method": sale.payment_method,
        "status": sale.status.value,
        "created_at": sale.created_at,
        "lines": lines,
    }


def return_response(db: Session, record: ReturnRecord) -> dict:
    refund = db.scalar(
        select(Refund)
        .where(Refund.return_id == record.id)
        .order_by(Refund.created_at.desc())
    )
    if refund is None:
        raise HTTPException(status_code=500, detail="Devolución sin reembolso asociado")
    return {
        "id": record.id,
        "sale_id": record.sale_id,
        "total": str(record.total),
        "refund": {
            "id": refund.id,
            "method": refund.method,
            "status": refund.status.value,
            "amount": str(refund.amount),
        },
    }


@post_sale_router.get("/sales")
def list_sales_for_post_sale(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*POST_SALE_READ_ROLES)),
) -> list[dict]:
    sales = db.scalars(
        select(Sale)
        .where(Sale.tenant_id == user.tenant_id)
        .order_by(Sale.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": sale.id,
            "branch_id": sale.branch_id,
            "total": str(sale.total),
            "payment_method": sale.payment_method,
            "status": sale.status.value,
            "created_at": sale.created_at,
        }
        for sale in sales
    ]


@post_sale_router.get("/sales/{sale_id}")
def get_sale_for_post_sale(
    sale_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*POST_SALE_READ_ROLES)),
) -> dict:
    sale = db.scalar(
        select(Sale).where(Sale.id == sale_id, Sale.tenant_id == user.tenant_id)
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    return sale_detail(db, sale)


@post_sale_router.get("/returns")
def list_returns(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*POST_SALE_READ_ROLES)),
) -> list[dict]:
    records = db.scalars(
        select(ReturnRecord)
        .where(ReturnRecord.tenant_id == user.tenant_id)
        .order_by(ReturnRecord.created_at.desc())
    ).all()
    return [
        {
            "id": item.id,
            "sale_id": item.sale_id,
            "reason": item.reason,
            "total": str(item.total),
            "created_at": item.created_at,
        }
        for item in records
    ]


@post_sale_router.post("/returns", status_code=201)
def create_return(
    payload: ReturnIn,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=100),
    ],
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*POST_SALE_WRITE_ROLES)),
) -> dict:
    request_hash = _return_hash(payload)
    existing = db.scalar(
        select(ReturnRecord).where(
            ReturnRecord.tenant_id == user.tenant_id,
            ReturnRecord.idempotency_key == idempotency_key,
        )
    )
    if existing:
        require_idempotency_match(existing.request_hash, request_hash)
        return return_response(db, existing)

    sale = db.scalar(
        select(Sale)
        .where(Sale.id == payload.sale_id, Sale.tenant_id == user.tenant_id)
        .with_for_update()
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    existing = db.scalar(
        select(ReturnRecord).where(
            ReturnRecord.tenant_id == user.tenant_id,
            ReturnRecord.idempotency_key == idempotency_key,
        )
    )
    if existing:
        require_idempotency_match(existing.request_hash, request_hash)
        return return_response(db, existing)

    cash_session = None
    if sale.payment_method == "cash":
        cash_session = db.scalar(
            select(CashSession)
            .where(
                CashSession.tenant_id == user.tenant_id,
                CashSession.branch_id == sale.branch_id,
                CashSession.user_id == user.id,
                CashSession.closed_at.is_(None),
            )
            .with_for_update()
        )
        if cash_session is None:
            raise HTTPException(
                status_code=409,
                detail="Debe abrir caja antes de reembolsar una venta en efectivo",
            )

    requested_ids = [line.sale_line_id for line in payload.lines]
    if len(requested_ids) != len(set(requested_ids)):
        raise HTTPException(
            status_code=422,
            detail="No repita una misma línea de venta en la devolución",
        )

    prepared: list[tuple[SaleLine, Decimal, Decimal]] = []
    total = Decimal("0")
    for item in sorted(payload.lines, key=lambda line: line.sale_line_id):
        sale_line = db.scalar(
            select(SaleLine)
            .where(SaleLine.id == item.sale_line_id, SaleLine.sale_id == sale.id)
            .with_for_update()
        )
        if not sale_line:
            raise HTTPException(status_code=404, detail="Línea de venta no encontrada")
        quantity = Decimal(item.quantity)
        returned = already_returned_quantity(db, sale_line.id)
        available_to_return = Decimal(sale_line.quantity) - returned
        if quantity > available_to_return:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Cantidad a devolver excede lo disponible. "
                    f"Máximo: {available_to_return}"
                ),
            )
        line_total = money(Decimal(sale_line.unit_price) * quantity)
        total += line_total
        prepared.append((sale_line, quantity, line_total))

    record = ReturnRecord(
        tenant_id=user.tenant_id,
        branch_id=sale.branch_id,
        sale_id=sale.id,
        created_by_user_id=user.id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        reason=payload.reason,
        total=money(total),
    )
    try:
        with db.begin_nested():
            db.add(record)
            db.flush()
    except IntegrityError:
        existing = db.scalar(
            select(ReturnRecord).where(
                ReturnRecord.tenant_id == user.tenant_id,
                ReturnRecord.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            raise
        require_idempotency_match(existing.request_hash, request_hash)
        return return_response(db, existing)

    for sale_line, quantity, line_total in prepared:
        db.add(
            ReturnLine(
                return_id=record.id,
                sale_line_id=sale_line.id,
                product_id=sale_line.product_id,
                quantity=quantity,
                unit_price=sale_line.unit_price,
                line_total=line_total,
            )
        )
        InventoryService.move(
            db,
            user,
            sale.branch_id,
            sale_line.product_id,
            quantity,
            "customer_return",
            "return",
            record.id,
        )

    refund_status = (
        RefundStatus.COMPLETED
        if sale.payment_method == "cash"
        else RefundStatus.PENDING_EXTERNAL
    )
    refund = Refund(
        tenant_id=user.tenant_id,
        return_id=record.id,
        amount=record.total,
        method=sale.payment_method,
        status=refund_status,
    )
    db.add(refund)
    db.flush()

    if cash_session is not None:
        db.add(
            CashMovement(
                tenant_id=user.tenant_id,
                branch_id=sale.branch_id,
                cash_session_id=cash_session.id,
                actor_user_id=user.id,
                movement_type="refund",
                amount=-record.total,
                reason=f"Reembolso en efectivo: {record.reason}",
                reference_type="refund",
                reference_id=refund.id,
            )
        )
        receipt = "\n".join(
            [
                "MILY ZEBRA",
                "DEVOLUCION / REEMBOLSO",
                "-" * 32,
                f"VENTA {sale.id[:8]}",
                f"DEVOLUCION {record.id[:8]}",
                f"TOTAL L {record.total}",
                "PAGO EFECTIVO",
            ]
        )
        db.add(
            PrintJob(
                tenant_id=user.tenant_id,
                branch_id=sale.branch_id,
                job_type="receipt",
                payload=json.dumps({"text": receipt}, ensure_ascii=False),
            )
        )
        db.add(
            PrintJob(
                tenant_id=user.tenant_id,
                branch_id=sale.branch_id,
                job_type="drawer",
                payload="{}",
            )
        )

    AuditService.record(
        db,
        user,
        "return.created",
        "return",
        record.id,
        {
            "sale_id": sale.id,
            "total": str(record.total),
            "refund_status": refund_status.value,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
        },
    )
    db.commit()
    return return_response(db, record)
