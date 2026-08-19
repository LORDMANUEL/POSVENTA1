from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.admin_api import device_claim_print_job
from app.admin_models import Device
from app.api import CashOpenIn, open_cash
from app.bank_reconciliation_api import MatchIn, match_transaction
from app.commerce_models import Order, OrderStatus, ReservationStatus, StockReservation
from app.db import SessionLocal
from app.finance_api import PaymentIn, receive_payment
from app.finance_models import BankAccount, BankTransaction, Receivable, ReceivablePayment
from app.models import (
    Branch,
    CashSession,
    InventoryMovement,
    PrintJob,
    Product,
    Sale,
    SaleLine,
    StockBalance,
    Tenant,
    User,
    UserRole,
)
from app.ops_api import receive_purchase
from app.ops_models import Customer, PurchaseOrder, PurchaseOrderLine, PurchaseStatus, Supplier
from app.post_sale_api import ReturnIn, ReturnLineIn, create_return
from app.post_sale_models import ReturnRecord
from app.services import SalesService


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _seed_core(stock: Decimal = Decimal("1")) -> dict[str, str]:
    with SessionLocal() as db:
        tenant = Tenant(name=_id("Tenant"), slug=_id("tenant"))
        db.add(tenant)
        db.flush()
        branch = Branch(tenant_id=tenant.id, code=_id("BR")[:30], name="Principal")
        db.add(branch)
        db.flush()
        user = User(
            tenant_id=tenant.id,
            branch_id=branch.id,
            email=f"{uuid.uuid4().hex}@example.com",
            full_name="Owner concurrency",
            password_hash="not-used",
            role=UserRole.OWNER,
        )
        product = Product(
            tenant_id=tenant.id,
            sku=_id("SKU"),
            name="Producto concurrente",
            sale_price=Decimal("100.00"),
            unit_cost=Decimal("50.00"),
        )
        db.add_all([user, product])
        db.flush()
        db.add(
            StockBalance(
                tenant_id=tenant.id,
                branch_id=branch.id,
                product_id=product.id,
                quantity=stock,
            )
        )
        db.commit()
        return {
            "tenant_id": tenant.id,
            "branch_id": branch.id,
            "user_id": user.id,
            "product_id": product.id,
        }


def _run_parallel(functions):
    with ThreadPoolExecutor(max_workers=len(functions)) as pool:
        futures = [pool.submit(fn) for fn in functions]
        return [future.result(timeout=20) for future in futures]


def test_two_sales_cannot_oversell_last_unit() -> None:
    ids = _seed_core(Decimal("1"))
    barrier = Barrier(2)

    def sell(key: str):
        with SessionLocal() as db:
            user = db.get(User, ids["user_id"])
            barrier.wait(timeout=10)
            try:
                sale = SalesService.create_sale(
                    db,
                    user,
                    ids["branch_id"],
                    key,
                    "transfer",
                    [{"product_id": ids["product_id"], "quantity": Decimal("1")}],
                )
                return ("ok", sale.id)
            except HTTPException as exc:
                db.rollback()
                return ("http", exc.status_code)

    results = _run_parallel([
        lambda: sell(_id("sale-a")),
        lambda: sell(_id("sale-b")),
    ])
    assert sum(result[0] == "ok" for result in results) == 1, results
    assert sorted(result[1] for result in results if result[0] == "http") == [409]

    with SessionLocal() as db:
        balance = db.scalar(
            select(StockBalance).where(
                StockBalance.tenant_id == ids["tenant_id"],
                StockBalance.branch_id == ids["branch_id"],
                StockBalance.product_id == ids["product_id"],
            )
        )
        assert Decimal(balance.quantity) == Decimal("0")
        movements = db.scalar(
            select(func.count(InventoryMovement.id)).where(
                InventoryMovement.tenant_id == ids["tenant_id"],
                InventoryMovement.product_id == ids["product_id"],
                InventoryMovement.reason == "sale",
            )
        )
        assert movements == 1


def test_pos_respects_active_ecommerce_reservations() -> None:
    ids = _seed_core(Decimal("1"))
    with SessionLocal() as db:
        customer = Customer(tenant_id=ids["tenant_id"], full_name="Cliente reservado")
        db.add(customer)
        db.flush()
        order = Order(
            tenant_id=ids["tenant_id"],
            branch_id=ids["branch_id"],
            customer_id=customer.id,
            idempotency_key=_id("reserved-order"),
            tracking_token_hash="c" * 64,
            status=OrderStatus.CONFIRMED,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            fulfillment_method="pickup",
        )
        db.add(order)
        db.flush()
        db.add(
            StockReservation(
                tenant_id=ids["tenant_id"],
                branch_id=ids["branch_id"],
                order_id=order.id,
                product_id=ids["product_id"],
                quantity=Decimal("1"),
                status=ReservationStatus.ACTIVE,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            )
        )
        db.commit()

    with SessionLocal() as db:
        user = db.get(User, ids["user_id"])
        with pytest.raises(HTTPException) as error:
            SalesService.create_sale(
                db,
                user,
                ids["branch_id"],
                _id("pos-reserved"),
                "transfer",
                [{"product_id": ids["product_id"], "quantity": Decimal("1")}],
            )
        db.rollback()
        assert error.value.status_code == 409

    with SessionLocal() as db:
        balance = db.scalar(
            select(StockBalance).where(
                StockBalance.tenant_id == ids["tenant_id"],
                StockBalance.branch_id == ids["branch_id"],
                StockBalance.product_id == ids["product_id"],
            )
        )
        assert Decimal(balance.quantity) == Decimal("1")


def test_concurrent_same_idempotency_key_creates_one_sale() -> None:
    ids = _seed_core(Decimal("2"))
    barrier = Barrier(2)
    key = _id("same-sale-key")

    def sell():
        with SessionLocal() as db:
            user = db.get(User, ids["user_id"])
            barrier.wait(timeout=10)
            sale = SalesService.create_sale(
                db,
                user,
                ids["branch_id"],
                key,
                "transfer",
                [{"product_id": ids["product_id"], "quantity": Decimal("1")}],
            )
            return sale.id

    sale_ids = _run_parallel([sell, sell])
    assert sale_ids[0] == sale_ids[1]
    with SessionLocal() as db:
        count = db.scalar(
            select(func.count(Sale.id)).where(
                Sale.tenant_id == ids["tenant_id"],
                Sale.idempotency_key == key,
            )
        )
        balance = db.scalar(
            select(StockBalance).where(
                StockBalance.tenant_id == ids["tenant_id"],
                StockBalance.branch_id == ids["branch_id"],
                StockBalance.product_id == ids["product_id"],
            )
        )
        assert count == 1
        assert Decimal(balance.quantity) == Decimal("1")


def test_open_cash_is_unique_under_concurrency() -> None:
    ids = _seed_core(Decimal("0"))
    barrier = Barrier(2)

    def open_one():
        with SessionLocal() as db:
            user = db.get(User, ids["user_id"])
            barrier.wait(timeout=10)
            try:
                result = open_cash(CashOpenIn(opening_amount=Decimal("50")), db=db, user=user)
                return ("ok", result["id"])
            except HTTPException as exc:
                db.rollback()
                return ("http", exc.status_code)

    results = _run_parallel([open_one, open_one])
    assert sum(result[0] == "ok" for result in results) == 1, results
    assert sum(result == ("http", 409) for result in results) == 1, results
    with SessionLocal() as db:
        count = db.scalar(
            select(func.count(CashSession.id)).where(
                CashSession.tenant_id == ids["tenant_id"],
                CashSession.user_id == ids["user_id"],
                CashSession.closed_at.is_(None),
            )
        )
        assert count == 1


def test_two_concurrent_returns_cannot_exceed_sold_quantity() -> None:
    ids = _seed_core(Decimal("0"))
    with SessionLocal() as db:
        sale = Sale(
            tenant_id=ids["tenant_id"],
            branch_id=ids["branch_id"],
            cashier_user_id=ids["user_id"],
            idempotency_key=_id("original-sale"),
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            payment_method="transfer",
        )
        db.add(sale)
        db.flush()
        line = SaleLine(
            sale_id=sale.id,
            product_id=ids["product_id"],
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            line_total=Decimal("100.00"),
        )
        db.add(line)
        db.commit()
        sale_id, line_id = sale.id, line.id

    barrier = Barrier(2)

    def return_one(key: str):
        with SessionLocal() as db:
            user = db.get(User, ids["user_id"])
            barrier.wait(timeout=10)
            try:
                return create_return(
                    ReturnIn(
                        sale_id=sale_id,
                        reason="Prueba concurrente",
                        lines=[ReturnLineIn(sale_line_id=line_id, quantity=Decimal("1"))],
                    ),
                    idempotency_key=key,
                    db=db,
                    user=user,
                )
            except HTTPException as exc:
                db.rollback()
                return {"error": exc.status_code}

    results = _run_parallel([
        lambda: return_one(_id("ret-a")),
        lambda: return_one(_id("ret-b")),
    ])
    assert sum("id" in result for result in results) == 1, results
    assert sum(result.get("error") == 409 for result in results) == 1, results
    with SessionLocal() as db:
        assert db.scalar(
            select(func.count(ReturnRecord.id)).where(ReturnRecord.sale_id == sale_id)
        ) == 1
        balance = db.scalar(
            select(StockBalance).where(
                StockBalance.tenant_id == ids["tenant_id"],
                StockBalance.branch_id == ids["branch_id"],
                StockBalance.product_id == ids["product_id"],
            )
        )
        assert Decimal(balance.quantity) == Decimal("1")


def test_receivable_balance_serializes_concurrent_payments() -> None:
    ids = _seed_core(Decimal("0"))
    with SessionLocal() as db:
        customer = Customer(tenant_id=ids["tenant_id"], full_name="Cliente concurrente")
        db.add(customer)
        db.flush()
        receivable = Receivable(
            tenant_id=ids["tenant_id"],
            customer_id=customer.id,
            reference=_id("AR"),
            original_amount=Decimal("1000.00"),
            balance=Decimal("1000.00"),
        )
        db.add(receivable)
        db.commit()
        receivable_id = receivable.id

    barrier = Barrier(2)

    def pay(amount: Decimal, key: str):
        with SessionLocal() as db:
            user = db.get(User, ids["user_id"])
            barrier.wait(timeout=10)
            try:
                return receive_payment(
                    receivable_id,
                    PaymentIn(amount=amount, method="transfer"),
                    idempotency_key=key,
                    db=db,
                    user=user,
                )
            except HTTPException as exc:
                db.rollback()
                return {"error": exc.status_code}

    results = _run_parallel([
        lambda: pay(Decimal("700.00"), _id("ar-a")),
        lambda: pay(Decimal("500.00"), _id("ar-b")),
    ])
    assert sum("id" in result for result in results) == 1, results
    assert sum(result.get("error") == 409 for result in results) == 1, results
    with SessionLocal() as db:
        item = db.get(Receivable, receivable_id)
        assert Decimal(item.balance) in {Decimal("300.00"), Decimal("500.00")}


def test_bank_match_target_is_unique_under_concurrency() -> None:
    ids = _seed_core(Decimal("0"))
    with SessionLocal() as db:
        customer = Customer(tenant_id=ids["tenant_id"], full_name="Cliente banco")
        db.add(customer)
        db.flush()
        receivable = Receivable(
            tenant_id=ids["tenant_id"],
            customer_id=customer.id,
            reference=_id("AR-BANK"),
            original_amount=Decimal("100.00"),
            balance=Decimal("0.00"),
            status="paid",
        )
        db.add(receivable)
        db.flush()
        payment = ReceivablePayment(
            tenant_id=ids["tenant_id"],
            receivable_id=receivable.id,
            idempotency_key=_id("payment"),
            request_hash="a" * 64,
            amount=Decimal("100.00"),
            method="transfer",
            received_by_user_id=ids["user_id"],
        )
        account = BankAccount(
            tenant_id=ids["tenant_id"],
            name=_id("bank"),
            bank_name="Banco",
        )
        db.add_all([payment, account])
        db.flush()
        txs = [
            BankTransaction(
                tenant_id=ids["tenant_id"],
                bank_account_id=account.id,
                transaction_date=date.today(),
                amount=Decimal("100.00"),
                external_reference=_id("tx"),
            )
            for _ in range(2)
        ]
        db.add_all(txs)
        db.commit()
        payment_id = payment.id
        tx_ids = [row.id for row in txs]

    barrier = Barrier(2)

    def match(tx_id: str):
        with SessionLocal() as db:
            user = db.get(User, ids["user_id"])
            barrier.wait(timeout=10)
            try:
                return match_transaction(
                    tx_id,
                    MatchIn(matched_type="receivable_payment", matched_id=payment_id),
                    db=db,
                    user=user,
                )
            except HTTPException as exc:
                db.rollback()
                return {"error": exc.status_code}

    results = _run_parallel([lambda: match(tx_ids[0]), lambda: match(tx_ids[1])])
    assert sum(result.get("status") == "matched" for result in results) == 1, results
    assert sum(result.get("error") == 409 for result in results) == 1, results


def test_purchase_receive_and_print_claim_are_single_effect() -> None:
    ids = _seed_core(Decimal("0"))
    with SessionLocal() as db:
        supplier = Supplier(tenant_id=ids["tenant_id"], name="Proveedor concurrency")
        db.add(supplier)
        db.flush()
        purchase = PurchaseOrder(
            tenant_id=ids["tenant_id"],
            branch_id=ids["branch_id"],
            supplier_id=supplier.id,
            created_by_user_id=ids["user_id"],
            status=PurchaseStatus.ORDERED,
        )
        db.add(purchase)
        db.flush()
        db.add(
            PurchaseOrderLine(
                purchase_order_id=purchase.id,
                product_id=ids["product_id"],
                quantity=Decimal("5"),
                unit_cost=Decimal("50"),
            )
        )
        devices = [
            Device(
                tenant_id=ids["tenant_id"],
                branch_id=ids["branch_id"],
                device_id=_id("device"),
                name="Caja",
                token_hash="b" * 64,
            )
            for _ in range(2)
        ]
        db.add_all(devices)
        db.flush()
        job = PrintJob(
            tenant_id=ids["tenant_id"],
            branch_id=ids["branch_id"],
            job_type="receipt",
            payload='{"text":"one"}',
        )
        db.add(job)
        db.commit()
        purchase_id = purchase.id
        device_ids = [d.id for d in devices]
        job_id = job.id

    barrier = Barrier(2)

    def receive():
        with SessionLocal() as db:
            user = db.get(User, ids["user_id"])
            barrier.wait(timeout=10)
            return receive_purchase(purchase_id, db=db, user=user)

    received = _run_parallel([receive, receive])
    assert all(row["status"] == "received" for row in received)
    with SessionLocal() as db:
        balance = db.scalar(
            select(StockBalance).where(
                StockBalance.tenant_id == ids["tenant_id"],
                StockBalance.branch_id == ids["branch_id"],
                StockBalance.product_id == ids["product_id"],
            )
        )
        assert Decimal(balance.quantity) == Decimal("5")
        assert db.scalar(
            select(func.count(InventoryMovement.id)).where(
                InventoryMovement.reference_type == "purchase_order",
                InventoryMovement.reference_id == purchase_id,
            )
        ) == 1

    claim_barrier = Barrier(2)

    def claim(device_id: str):
        with SessionLocal() as db:
            device = db.get(Device, device_id)
            claim_barrier.wait(timeout=10)
            return device_claim_print_job(db=db, device=device)

    claims = _run_parallel([
        lambda: claim(device_ids[0]),
        lambda: claim(device_ids[1]),
    ])
    claimed = [row for row in claims if row is not None]
    assert len(claimed) == 1, claims
    assert claimed[0]["id"] == job_id
