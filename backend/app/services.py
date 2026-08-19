from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .cash_models import CashMovement
from .commerce_models import ReservationStatus, StockReservation
from .integrity import (
    canonical_request_hash,
    require_branch_scope,
    require_idempotency_match,
)
from .models import (
    AuditEvent,
    CashSession,
    InventoryMovement,
    PrintJob,
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
    def get_or_create_balance(
        db: Session,
        user: User,
        branch_id: str,
        product_id: str,
    ) -> StockBalance:
        require_branch_scope(db, user.tenant_id, branch_id)
        scope = (
            StockBalance.tenant_id == user.tenant_id,
            StockBalance.branch_id == branch_id,
            StockBalance.product_id == product_id,
        )

        if db.get_bind().dialect.name == "postgresql":
            db.execute(
                pg_insert(StockBalance)
                .values(
                    tenant_id=user.tenant_id,
                    branch_id=branch_id,
                    product_id=product_id,
                    quantity=Decimal("0"),
                )
                .on_conflict_do_nothing(
                    index_elements=["tenant_id", "branch_id", "product_id"]
                )
            )
            balance = db.scalar(select(StockBalance).where(*scope).with_for_update())
            if balance is None:
                raise RuntimeError("No se pudo bloquear el saldo de inventario")
            return balance

        balance = db.scalar(select(StockBalance).where(*scope))
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
        require_branch_scope(db, user.tenant_id, branch_id)
        product = db.scalar(
            select(Product).where(
                Product.id == product_id,
                Product.tenant_id == user.tenant_id,
            )
        )
        if product is None:
            raise HTTPException(status_code=404, detail="Producto no encontrado")

        balance = cls.get_or_create_balance(db, user, branch_id, product_id)
        delta = Decimal(quantity_delta)
        new_quantity = Decimal(balance.quantity) + delta
        if prevent_negative and delta < 0:
            reservation_query = select(func.coalesce(func.sum(StockReservation.quantity), 0)).where(
                StockReservation.tenant_id == user.tenant_id,
                StockReservation.branch_id == branch_id,
                StockReservation.product_id == product_id,
                StockReservation.status == ReservationStatus.ACTIVE,
                StockReservation.expires_at > datetime.now(timezone.utc),
            )
            if reference_type == "order" and reference_id:
                reservation_query = reservation_query.where(
                    StockReservation.order_id != reference_id
                )
            reserved = Decimal(db.scalar(reservation_query) or 0)
            available = Decimal(balance.quantity) - reserved
            if -delta > available:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Stock insuficiente para {product.name}; "
                        f"disponible no reservado: {available}"
                    ),
                )
        elif prevent_negative and new_quantity < 0:
            raise HTTPException(
                status_code=409,
                detail=f"Stock insuficiente para {product.name}",
            )

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
    def _receipt_text(
        sale: Sale,
        prepared: list[tuple[Product, Decimal]],
    ) -> str:
        lines = ["MILY ZEBRA", "Roatan, Islas de la Bahia", "-" * 32]
        for product, quantity in prepared:
            total = money(Decimal(product.sale_price) * quantity)
            lines.append(f"{product.name[:24]}")
            lines.append(
                f" {quantity} x {money(Decimal(product.sale_price))} = {total}"
            )
        lines.extend(
            [
                "-" * 32,
                f"TOTAL L {sale.total}",
                f"PAGO {sale.payment_method.upper()}",
                f"VENTA {sale.id[:8]}",
                "Gracias por elegir Mily Zebra",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _request_hash(
        branch_id: str,
        payment_method: str,
        lines: list[dict],
    ) -> str:
        normalized = [
            {
                "product_id": str(item["product_id"]),
                "quantity": Decimal(str(item["quantity"])),
            }
            for item in lines
        ]
        normalized.sort(key=lambda item: item["product_id"])
        return canonical_request_hash(
            {
                "branch_id": branch_id,
                "payment_method": payment_method,
                "lines": normalized,
            }
        )

    @staticmethod
    def create_sale(
        db: Session,
        user: User,
        branch_id: str,
        idempotency_key: str,
        payment_method: str,
        lines: list[dict],
    ) -> Sale:
        if not lines:
            raise HTTPException(
                status_code=422,
                detail="La venta debe incluir al menos un producto",
            )
        product_ids = [str(item["product_id"]) for item in lines]
        if len(product_ids) != len(set(product_ids)):
            raise HTTPException(
                status_code=422,
                detail="Un producto no debe repetirse en la misma venta",
            )

        require_branch_scope(db, user.tenant_id, branch_id, active_only=True)
        request_hash = SalesService._request_hash(
            branch_id,
            payment_method,
            lines,
        )
        existing = db.scalar(
            select(Sale).where(
                Sale.tenant_id == user.tenant_id,
                Sale.idempotency_key == idempotency_key,
            )
        )
        if existing:
            require_idempotency_match(existing.request_hash, request_hash)
            return existing

        cash_session = None
        if payment_method == "cash":
            cash_session = db.scalar(
                select(CashSession)
                .where(
                    CashSession.tenant_id == user.tenant_id,
                    CashSession.branch_id == branch_id,
                    CashSession.user_id == user.id,
                    CashSession.closed_at.is_(None),
                )
                .with_for_update()
            )
            if not cash_session:
                raise HTTPException(
                    status_code=409,
                    detail="Debe abrir caja antes de realizar una venta en efectivo",
                )

        sale = Sale(
            tenant_id=user.tenant_id,
            branch_id=branch_id,
            cashier_user_id=user.id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            subtotal=Decimal("0"),
            discount_total=Decimal("0"),
            tax_total=Decimal("0"),
            total=Decimal("0"),
            payment_method=payment_method,
        )

        try:
            with db.begin_nested():
                db.add(sale)
                db.flush()
        except IntegrityError:
            existing = db.scalar(
                select(Sale).where(
                    Sale.tenant_id == user.tenant_id,
                    Sale.idempotency_key == idempotency_key,
                )
            )
            if existing is None:
                raise
            require_idempotency_match(existing.request_hash, request_hash)
            return existing

        subtotal = Decimal("0")
        prepared: list[tuple[Product, Decimal]] = []
        for item in sorted(lines, key=lambda value: str(value["product_id"])):
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
                raise HTTPException(
                    status_code=422,
                    detail="La cantidad debe ser mayor que cero",
                )
            prepared.append((product, quantity))

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

        if cash_session:
            db.add(
                CashMovement(
                    tenant_id=user.tenant_id,
                    branch_id=branch_id,
                    cash_session_id=cash_session.id,
                    actor_user_id=user.id,
                    movement_type="sale",
                    amount=sale.total,
                    reason="Venta en efectivo",
                    reference_type="sale",
                    reference_id=sale.id,
                )
            )

        db.add(
            PrintJob(
                tenant_id=user.tenant_id,
                branch_id=branch_id,
                job_type="receipt",
                payload=json.dumps(
                    {"text": SalesService._receipt_text(sale, prepared)},
                    ensure_ascii=False,
                ),
            )
        )
        if payment_method == "cash":
            db.add(
                PrintJob(
                    tenant_id=user.tenant_id,
                    branch_id=branch_id,
                    job_type="drawer",
                    payload="{}",
                )
            )

        AuditService.record(
            db,
            user,
            "sale.created",
            "sale",
            sale.id,
            {
                "total": str(sale.total),
                "payment_method": payment_method,
                "idempotency_key": idempotency_key,
                "request_hash": request_hash,
            },
        )
        db.commit()
        db.refresh(sale)
        return sale
