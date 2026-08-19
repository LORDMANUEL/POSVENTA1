from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Sale, SaleLine, User, UserRole
from .post_sale_models import Refund, RefundStatus, ReturnLine, ReturnRecord
from .security import require_roles
from .services import AuditService, InventoryService, money

post_sale_router = APIRouter(prefix="/post-sales", tags=["post-sales"])


class ReturnLineIn(BaseModel):
    sale_line_id: str
    quantity: Decimal = Field(gt=0)


class ReturnIn(BaseModel):
    sale_id: str
    reason: str = Field(min_length=3, max_length=240)
    lines: list[ReturnLineIn] = Field(min_length=1)


def already_returned_quantity(db: Session, sale_line_id: str) -> Decimal:
    value = db.scalar(select(func.coalesce(func.sum(ReturnLine.quantity), 0)).where(ReturnLine.sale_line_id == sale_line_id))
    return Decimal(value or 0)


@post_sale_router.get("/returns")
def list_returns(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.CASHIER, UserRole.AUDITOR)),
) -> list[dict]:
    records = db.scalars(select(ReturnRecord).where(ReturnRecord.tenant_id == user.tenant_id).order_by(ReturnRecord.created_at.desc())).all()
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
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.CASHIER)),
) -> dict:
    sale = db.scalar(select(Sale).where(Sale.id == payload.sale_id, Sale.tenant_id == user.tenant_id))
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    requested_ids = [line.sale_line_id for line in payload.lines]
    if len(requested_ids) != len(set(requested_ids)):
        raise HTTPException(status_code=422, detail="No repita una misma línea de venta en la devolución")

    prepared: list[tuple[SaleLine, Decimal, Decimal]] = []
    total = Decimal("0")
    for item in payload.lines:
        sale_line = db.scalar(select(SaleLine).where(SaleLine.id == item.sale_line_id, SaleLine.sale_id == sale.id))
        if not sale_line:
            raise HTTPException(status_code=404, detail="Línea de venta no encontrada")
        quantity = Decimal(item.quantity)
        returned = already_returned_quantity(db, sale_line.id)
        available_to_return = Decimal(sale_line.quantity) - returned
        if quantity > available_to_return:
            raise HTTPException(
                status_code=409,
                detail=f"Cantidad a devolver excede lo disponible. Máximo: {available_to_return}",
            )
        line_total = money(Decimal(sale_line.unit_price) * quantity)
        total += line_total
        prepared.append((sale_line, quantity, line_total))

    record = ReturnRecord(
        tenant_id=user.tenant_id,
        branch_id=sale.branch_id,
        sale_id=sale.id,
        created_by_user_id=user.id,
        reason=payload.reason,
        total=money(total),
    )
    db.add(record)
    db.flush()

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

    refund_status = RefundStatus.COMPLETED if sale.payment_method == "cash" else RefundStatus.PENDING_EXTERNAL
    refund = Refund(
        tenant_id=user.tenant_id,
        return_id=record.id,
        amount=record.total,
        method=sale.payment_method,
        status=refund_status,
    )
    db.add(refund)
    AuditService.record(
        db,
        user,
        "return.created",
        "return",
        record.id,
        {"sale_id": sale.id, "total": str(record.total), "refund_status": refund_status.value},
    )
    db.commit()
    return {
        "id": record.id,
        "sale_id": sale.id,
        "total": str(record.total),
        "refund": {
            "id": refund.id,
            "method": refund.method,
            "status": refund.status.value,
            "amount": str(refund.amount),
        },
    }
