from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .accounting_models import Account, JournalEntry, JournalLine
from .finance_models import Payable
from .models import AuditEvent, Product, User
from .module_registry import TenantModule

CENT = Decimal("0.01")

SYSTEM_ACCOUNTS: dict[str, tuple[str, str]] = {
    "1100": ("Caja", "asset"),
    "1110": ("Pagos por acreditar", "asset"),
    "1200": ("Cuentas por cobrar", "asset"),
    "1300": ("Inventario", "asset"),
    "2000": ("Cuentas por pagar", "liability"),
    "4000": ("Ventas", "income"),
    "4010": ("Devoluciones sobre ventas", "income"),
    "5000": ("Costo de ventas", "expense"),
}


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT)


def _module_enabled(db: Session, tenant_id: str, key: str, *, default: bool = True) -> bool:
    row = db.scalar(
        select(TenantModule).where(
            TenantModule.tenant_id == tenant_id,
            TenantModule.module_key == key,
        )
    )
    return default if row is None else bool(row.enabled)


def _audit(
    db: Session,
    user: User,
    action: str,
    entity_type: str,
    entity_id: str,
    metadata: dict,
) -> None:
    import json

    db.add(
        AuditEvent(
            tenant_id=user.tenant_id,
            actor_user_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=json.dumps(metadata, ensure_ascii=False, default=str),
        )
    )


class AccountingIntegrationService:
    @staticmethod
    def enabled(db: Session, tenant_id: str) -> bool:
        return _module_enabled(db, tenant_id, "accounting", default=True)

    @staticmethod
    def _ensure_account(db: Session, tenant_id: str, code: str) -> Account:
        if code not in SYSTEM_ACCOUNTS:
            raise ValueError(f"Cuenta de sistema no registrada: {code}")
        name, account_type = SYSTEM_ACCOUNTS[code]
        account = db.scalar(
            select(Account).where(Account.tenant_id == tenant_id, Account.code == code)
        )
        if account is None and db.get_bind().dialect.name == "postgresql":
            db.execute(
                pg_insert(Account)
                .values(
                    tenant_id=tenant_id,
                    code=code,
                    name=name,
                    account_type=account_type,
                    system=True,
                    active=True,
                )
                .on_conflict_do_nothing(index_elements=["tenant_id", "code"])
            )
            account = db.scalar(
                select(Account).where(Account.tenant_id == tenant_id, Account.code == code)
            )
        elif account is None:
            account = Account(
                tenant_id=tenant_id,
                code=code,
                name=name,
                account_type=account_type,
                system=True,
                active=True,
            )
            db.add(account)
            db.flush()

        if account is None:
            raise RuntimeError(f"No se pudo crear la cuenta de sistema {code}")
        if account.account_type != account_type:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"La cuenta reservada {code} existe con tipo {account.account_type}; "
                    f"se esperaba {account_type}"
                ),
            )
        if not account.active:
            raise HTTPException(
                status_code=409,
                detail=f"La cuenta reservada {code} está inactiva",
            )
        if not account.system:
            account.system = True
        return account

    @classmethod
    def _post(
        cls,
        db: Session,
        user: User,
        *,
        reference: str,
        description: str,
        source_type: str,
        source_id: str,
        branch_id: str | None,
        lines: list[tuple[str, Decimal, Decimal, str]],
    ) -> JournalEntry | None:
        if not cls.enabled(db, user.tenant_id):
            return None
        existing = db.scalar(
            select(JournalEntry).where(
                JournalEntry.tenant_id == user.tenant_id,
                JournalEntry.reference == reference,
            )
        )
        if existing is not None:
            return existing

        debit = sum((_money(line[1]) for line in lines), Decimal("0"))
        credit = sum((_money(line[2]) for line in lines), Decimal("0"))
        if debit != credit or debit <= 0:
            raise HTTPException(
                status_code=409,
                detail=f"Asiento automático desbalanceado {reference}: {debit} != {credit}",
            )

        accounts = {code: cls._ensure_account(db, user.tenant_id, code) for code, *_ in lines}
        entry = JournalEntry(
            tenant_id=user.tenant_id,
            reference=reference,
            description=description,
            source_type=source_type,
            source_id=source_id,
            status="posted",
            posted_at=datetime.now(timezone.utc),
            posted_by_user_id=user.id,
        )
        try:
            with db.begin_nested():
                db.add(entry)
                db.flush()
        except IntegrityError:
            existing = db.scalar(
                select(JournalEntry).where(
                    JournalEntry.tenant_id == user.tenant_id,
                    JournalEntry.reference == reference,
                )
            )
            if existing is not None:
                return existing
            raise

        for code, line_debit, line_credit, memo in lines:
            db.add(
                JournalLine(
                    journal_entry_id=entry.id,
                    account_id=accounts[code].id,
                    branch_id=branch_id,
                    memo=memo,
                    debit=_money(line_debit),
                    credit=_money(line_credit),
                )
            )
        _audit(
            db,
            user,
            "journal.auto_posted",
            "journal_entry",
            entry.id,
            {
                "reference": reference,
                "source_type": source_type,
                "source_id": source_id,
                "debit": str(debit),
                "credit": str(credit),
            },
        )
        return entry

    @classmethod
    def post_sale(
        cls,
        db: Session,
        user: User,
        sale,
        prepared: list[tuple[Product, Decimal]],
    ) -> JournalEntry | None:
        revenue = _money(Decimal(sale.total))
        cost = _money(
            sum(
                (Decimal(product.unit_cost) * Decimal(quantity) for product, quantity in prepared),
                Decimal("0"),
            )
        )
        settlement_account = "1100" if sale.payment_method == "cash" else "1110"
        lines: list[tuple[str, Decimal, Decimal, str]] = [
            (settlement_account, revenue, Decimal("0"), "Cobro de venta"),
            ("4000", Decimal("0"), revenue, "Ingreso por venta"),
        ]
        if cost > 0:
            lines.extend(
                [
                    ("5000", cost, Decimal("0"), "Costo de venta"),
                    ("1300", Decimal("0"), cost, "Salida de inventario por venta"),
                ]
            )
        return cls._post(
            db,
            user,
            reference=f"SALE:{sale.id}",
            description=f"Venta {sale.id}",
            source_type="sale",
            source_id=sale.id,
            branch_id=sale.branch_id,
            lines=lines,
        )

    @classmethod
    def post_purchase_receipt(
        cls,
        db: Session,
        user: User,
        purchase,
    ) -> JournalEntry | None:
        total = _money(
            sum(
                (Decimal(line.quantity) * Decimal(line.unit_cost) for line in purchase.lines),
                Decimal("0"),
            )
        )
        if total <= 0:
            return None
        entry = cls._post(
            db,
            user,
            reference=f"PURCHASE:{purchase.id}",
            description=f"Recepción de compra {purchase.id}",
            source_type="purchase_receipt",
            source_id=purchase.id,
            branch_id=purchase.branch_id,
            lines=[
                ("1300", total, Decimal("0"), "Entrada de inventario"),
                ("2000", Decimal("0"), total, "Obligación con proveedor"),
            ],
        )
        if _module_enabled(db, user.tenant_id, "payables", default=True):
            reference = f"PO:{purchase.id}"
            existing = db.scalar(
                select(Payable).where(
                    Payable.tenant_id == user.tenant_id,
                    Payable.reference == reference,
                )
            )
            if existing is None:
                payable = Payable(
                    tenant_id=user.tenant_id,
                    supplier_id=purchase.supplier_id,
                    reference=reference,
                    description=f"Cuenta por pagar de recepción {purchase.id}",
                    original_amount=total,
                    balance=total,
                    status="open",
                )
                db.add(payable)
                db.flush()
                _audit(
                    db,
                    user,
                    "payable.auto_created",
                    "payable",
                    payable.id,
                    {"purchase_id": purchase.id, "amount": str(total)},
                )
        return entry

    @classmethod
    def post_return(
        cls,
        db: Session,
        user: User,
        record,
        prepared,
        payment_method: str,
    ) -> JournalEntry | None:
        revenue = _money(Decimal(record.total))
        cost = Decimal("0")
        for sale_line, quantity, _line_total in prepared:
            product = db.scalar(
                select(Product).where(
                    Product.id == sale_line.product_id,
                    Product.tenant_id == user.tenant_id,
                )
            )
            if product is None:
                raise HTTPException(status_code=404, detail="Producto de devolución no encontrado")
            cost += Decimal(product.unit_cost) * Decimal(quantity)
        cost = _money(cost)
        settlement_account = "1100" if payment_method == "cash" else "1110"
        lines: list[tuple[str, Decimal, Decimal, str]] = [
            ("4010", revenue, Decimal("0"), "Devolución sobre venta"),
            (settlement_account, Decimal("0"), revenue, "Reembolso al cliente"),
        ]
        if cost > 0:
            lines.extend(
                [
                    ("1300", cost, Decimal("0"), "Reingreso de inventario"),
                    ("5000", Decimal("0"), cost, "Reversa de costo de venta"),
                ]
            )
        return cls._post(
            db,
            user,
            reference=f"RETURN:{record.id}",
            description=f"Devolución {record.id}",
            source_type="return",
            source_id=record.id,
            branch_id=record.branch_id,
            lines=lines,
        )

    @classmethod
    def post_order_revenue(
        cls,
        db: Session,
        user: User,
        order,
        payment_method: str,
    ) -> JournalEntry | None:
        total = _money(Decimal(order.total))
        settlement_account = "1100" if payment_method == "cash_on_delivery" else "1110"
        return cls._post(
            db,
            user,
            reference=f"ORDER-REVENUE:{order.id}",
            description=f"Ingreso ecommerce {order.id}",
            source_type="order_payment",
            source_id=order.id,
            branch_id=order.branch_id,
            lines=[
                (settlement_account, total, Decimal("0"), "Cobro ecommerce"),
                ("4000", Decimal("0"), total, "Ingreso ecommerce"),
            ],
        )

    @classmethod
    def post_order_cogs(
        cls,
        db: Session,
        user: User,
        order,
    ) -> JournalEntry | None:
        cost = Decimal("0")
        for line in order.lines:
            product = db.scalar(
                select(Product).where(
                    Product.id == line.product_id,
                    Product.tenant_id == user.tenant_id,
                )
            )
            if product is None:
                raise HTTPException(status_code=404, detail="Producto de pedido no encontrado")
            cost += Decimal(product.unit_cost) * Decimal(line.quantity)
        cost = _money(cost)
        if cost <= 0:
            return None
        return cls._post(
            db,
            user,
            reference=f"ORDER-COGS:{order.id}",
            description=f"Costo ecommerce {order.id}",
            source_type="order_fulfillment",
            source_id=order.id,
            branch_id=order.branch_id,
            lines=[
                ("5000", cost, Decimal("0"), "Costo de pedido ecommerce"),
                ("1300", Decimal("0"), cost, "Salida de inventario ecommerce"),
            ],
        )
