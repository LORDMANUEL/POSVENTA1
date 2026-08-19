import json
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AuditEvent,
    InventoryMovement,
    Product,
    Sale,
    SaleLine,
    StockBalance,
    User,
)


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


class AuditService:
    @staticmethod
    def record(
        db: Session,
        user: User,
        action: str,
        entity_type: str,
        entity_id: str | None,
        metadata: dict | None = None,
    ) -> None:
        db.add(
            AuditEvent(
                tenant_id=user.tenant_id,
                actor_user_id=user.id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False, default=str),
            )
        )


class InventoryService:
    @staticmethod
    def get_or_create_balance(db: Session, user: User, branch_id: str, product_id: str) -> StockBalance:
        balance = db.scalar(
            select(StockBalance).where(
                StockBalance.tenant_id == user.tenant_id,
                StockBalance.branch_id == branch_id,
                StockBalance.product_id == product_id,
            )
        )
        if balance is None:
            balance = StockBalance(
                tenant_id=user.tenant_id,
                branch_id=branch_id,
                product_id=product_id,
                quantity=Decimal("0"),
            )
            db.add(balance)
            db.flush()
        return balance

    @classmethod
    def move(
        cls,
        db: Session,
        user: User,
        branch_id: str,
        product_id: str,
        quantity_delta: Decimal,
        reason: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
        prevent_negative: bool = False,
    ) -> StockBalance:
        product = db.scalar(
            select(Product).where(Product.id == product_id, Product.tenant_id == user.tenant_id)
        )
        if product is None:
            raise HTTPException(status_code=404, detail="Producto no encontrado")

        balance = cls.get_or_create_balance(db, user, branch_id, product_id)
        new_quantity = Decimal(balance.quantity) + Decimal(quantity_delta)
        if prevent_negative and new_quantity < 0:
            raise HTTPException(status_code=409, detail=f"Stock insuficiente para {product.name}")

        balance.quantity = new_quantity
        balance.updated_at = datetime.now(timezone.utc)
        db.add(
            InventoryMovement(
                tenant_id=user.tenant_id,
                branch_id=branch_id,
                product_id=product_id,
                quantity_delta=quantity_delta,
                reason=reason,
                reference_type=reference_type,
                reference_id=reference_id,
                actor_user_id=user.id,
            )
        )
        return balance


class SalesService:
    @staticmethod
    def create_sale(
        db: Session,
        user: User,
        branch_id: str,
        idempotency_key: str,
        payment_method: str,
        lines: list[dict],
    ) -> Sale:
        existing = db.scalar(
            select(Sale).where(
                Sale.tenant_id == user.tenant_id,
                Sale.idempotency_key == idempotency_key,
            )
        )
        if existing:
            return existing
        if not lines:
            raise HTTPException(status_code=422, detail="La venta debe incluir al menos un producto")

        sale = Sale(
            tenant_id=user.tenant_id,
            branch_id=branch_id,
            cashier_user_id=user.id,
            idempotency_key=idempotency_key,
            subtotal=Decimal("0"),
            discount_total=Decimal("0"),
            tax_total=Decimal("0"),
            total=Decimal("0"),
            payment_method=payment_method,
        )
        db.add(sale)
        db.flush()

        subtotal = Decimal("0")
        prepared: list[tuple[Product, Decimal]] = []
        for item in lines:
            product = db.scalar(
                select(Product).where(
                    Product.id == item["product_id"],
                    Product.tenant_id == user.tenant_id,
                    Product.active.is_(True),
                )
            )
            if product is None:
                raise HTTPException(status_code=404, detail="Producto no encontrado")
            quantity = Decimal(str(item["quantity"]))
            if quantity <= 0:
                raise HTTPException(status_code=422, detail="La cantidad debe ser mayor que cero")
            prepared.append((product, quantity))

        # Validate and deduct within the same DB transaction.
        for product, quantity in prepared:
            InventoryService.move(
                db,
                user,
                branch_id,
                product.id,
                -quantity,
                "sale",
                "sale",
                sale.id,
                prevent_negative=True,
            )
            line_total = money(Decimal(product.sale_price) * quantity)
            subtotal += line_total
            db.add(
                SaleLine(
                    sale_id=sale.id,
                    product_id=product.id,
                    quantity=quantity,
                    unit_price=product.sale_price,
                    line_total=line_total,
                )
            )

        sale.subtotal = money(subtotal)
        sale.total = money(subtotal)
        AuditService.record(
            db,
            user,
            "sale.created",
            "sale",
            sale.id,
            {"total": str(sale.total), "payment_method": payment_method},
        )
        db.commit()
        db.refresh(sale)
        return sale
