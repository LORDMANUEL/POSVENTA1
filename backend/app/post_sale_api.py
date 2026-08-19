from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Product, Sale, SaleLine, User, UserRole
from .post_sale_models import Refund, RefundStatus, ReturnLine, ReturnRecord
from .security import require_roles
from .services import AuditService, InventoryService, money

post_sale_router = APIRouter(prefix="/post-sales", tags=["post-sales"])
POST_SALE_READ_ROLES = (UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.CASHIER, UserRole.AUDITOR)
POST_SALE_WRITE_ROLES = (UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.CASHIER)


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
    value = db.scalar(select(func.coalesce(func.sum(ReturnLine.quantity), 0)).where(ReturnLine.sale_line_id == sale_line_id))
    return Decimal(value or 0)


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
    sale = db.scalar(select(Sale).where(Sale.id == sale_id, Sale.tenant_id == user.tenant_id))
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    return sale_detail(db, sale)


@post_sale_router.get("/returns")
def list_returns(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*POST_SALE_READ_ROLES)),
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
    user: User = Depends(require_roles(*POST_SALE_WRITE_ROLES)),
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
