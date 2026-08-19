from decimal import Decimal

from sqlalchemy import func, select

from app.accounting_models import Account, JournalEntry, JournalLine
from app.db import SessionLocal
from app.finance_models import Payable


def _entry_snapshot(reference: str) -> dict:
    with SessionLocal() as db:
        entry = db.scalar(select(JournalEntry).where(JournalEntry.reference == reference))
        assert entry is not None, reference
        lines = db.execute(
            select(JournalLine, Account)
            .join(Account, Account.id == JournalLine.account_id)
            .where(JournalLine.journal_entry_id == entry.id)
            .order_by(Account.code)
        ).all()
        return {
            "status": entry.status,
            "source_type": entry.source_type,
            "source_id": entry.source_id,
            "lines": {
                account.code: {
                    "debit": Decimal(line.debit),
                    "credit": Decimal(line.credit),
                }
                for line, account in lines
            },
        }


def _create_product(client, headers, sku: str, cost: str = "40.00", price: str = "100.00") -> str:
    response = client.post(
        "/products",
        headers=headers,
        json={
            "sku": sku,
            "name": f"Producto {sku}",
            "unit_cost": cost,
            "sale_price": price,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _stock(client, headers, product_id: str, quantity: str = "5") -> None:
    response = client.post(
        "/inventory/movements",
        headers=headers,
        json={
            "product_id": product_id,
            "quantity_delta": quantity,
            "reason": "accounting_integration_seed",
        },
    )
    assert response.status_code == 200, response.text


def test_cash_sale_posts_revenue_and_cogs_once(client, owner_headers) -> None:
    product_id = _create_product(client, owner_headers, "AUTO-ACC-SALE")
    _stock(client, owner_headers, product_id)
    opened = client.post(
        "/cash/open",
        headers=owner_headers,
        json={"opening_amount": "50.00"},
    )
    assert opened.status_code == 201, opened.text

    headers = {**owner_headers, "Idempotency-Key": "auto-accounting-sale-0001"}
    payload = {
        "payment_method": "cash",
        "lines": [{"product_id": product_id, "quantity": "1"}],
    }
    sold = client.post("/sales", headers=headers, json=payload)
    assert sold.status_code == 201, sold.text
    repeated = client.post("/sales", headers=headers, json=payload)
    assert repeated.status_code == 201
    assert repeated.json()["id"] == sold.json()["id"]

    reference = f"SALE:{sold.json()['id']}"
    entry = _entry_snapshot(reference)
    assert entry["status"] == "posted"
    assert entry["source_type"] == "sale"
    assert entry["lines"]["1100"] == {"debit": Decimal("100.00"), "credit": Decimal("0")}
    assert entry["lines"]["4000"] == {"debit": Decimal("0"), "credit": Decimal("100.00")}
    assert entry["lines"]["5000"] == {"debit": Decimal("40.00"), "credit": Decimal("0")}
    assert entry["lines"]["1300"] == {"debit": Decimal("0"), "credit": Decimal("40.00")}

    with SessionLocal() as db:
        count = db.scalar(select(func.count(JournalEntry.id)).where(JournalEntry.reference == reference))
        assert count == 1


def test_purchase_receipt_posts_inventory_ap_and_creates_payable_once(client, owner_headers) -> None:
    product_id = _create_product(client, owner_headers, "AUTO-ACC-PO", cost="30.00", price="80.00")
    supplier = client.post(
        "/ops/suppliers",
        headers=owner_headers,
        json={"name": "Proveedor integración contable"},
    )
    assert supplier.status_code == 201, supplier.text
    purchase = client.post(
        "/ops/purchases",
        headers=owner_headers,
        json={
            "supplier_id": supplier.json()["id"],
            "lines": [{"product_id": product_id, "quantity": "3", "unit_cost": "25.00"}],
        },
    )
    assert purchase.status_code == 201, purchase.text
    purchase_id = purchase.json()["id"]

    first = client.post(f"/ops/purchases/{purchase_id}/receive", headers=owner_headers)
    assert first.status_code == 200, first.text
    second = client.post(f"/ops/purchases/{purchase_id}/receive", headers=owner_headers)
    assert second.status_code == 200

    entry = _entry_snapshot(f"PURCHASE:{purchase_id}")
    assert entry["status"] == "posted"
    assert entry["source_type"] == "purchase_receipt"
    assert entry["lines"]["1300"] == {"debit": Decimal("75.00"), "credit": Decimal("0")}
    assert entry["lines"]["2000"] == {"debit": Decimal("0"), "credit": Decimal("75.00")}

    with SessionLocal() as db:
        payable = db.scalar(select(Payable).where(Payable.reference == f"PO:{purchase_id}"))
        assert payable is not None
        assert Decimal(payable.original_amount) == Decimal("75.00")
        assert Decimal(payable.balance) == Decimal("75.00")
        assert db.scalar(
            select(func.count(Payable.id)).where(Payable.reference == f"PO:{purchase_id}")
        ) == 1


def test_return_posts_sales_and_cogs_reversal(client, owner_headers) -> None:
    product_id = _create_product(client, owner_headers, "AUTO-ACC-RETURN")
    _stock(client, owner_headers, product_id, "2")
    opened = client.post(
        "/cash/open",
        headers=owner_headers,
        json={"opening_amount": "0"},
    )
    assert opened.status_code == 201
    sale = client.post(
        "/sales",
        headers={**owner_headers, "Idempotency-Key": "auto-accounting-return-sale"},
        json={"payment_method": "cash", "lines": [{"product_id": product_id, "quantity": "1"}]},
    )
    assert sale.status_code == 201, sale.text
    detail = client.get(f"/post-sales/sales/{sale.json()['id']}", headers=owner_headers)
    line_id = detail.json()["lines"][0]["sale_line_id"]
    returned = client.post(
        "/post-sales/returns",
        headers={**owner_headers, "Idempotency-Key": "auto-accounting-return-0001"},
        json={
            "sale_id": sale.json()["id"],
            "reason": "Prueba de reversa contable",
            "lines": [{"sale_line_id": line_id, "quantity": "1"}],
        },
    )
    assert returned.status_code == 201, returned.text

    entry = _entry_snapshot(f"RETURN:{returned.json()['id']}")
    assert entry["status"] == "posted"
    assert entry["source_type"] == "return"
    assert entry["lines"]["4010"] == {"debit": Decimal("100.00"), "credit": Decimal("0")}
    assert entry["lines"]["1100"] == {"debit": Decimal("0"), "credit": Decimal("100.00")}
    assert entry["lines"]["1300"] == {"debit": Decimal("40.00"), "credit": Decimal("0")}
    assert entry["lines"]["5000"] == {"debit": Decimal("0"), "credit": Decimal("40.00")}


def test_ecommerce_paid_and_fulfilled_posts_revenue_and_cogs(client, owner_headers) -> None:
    product_id = _create_product(client, owner_headers, "AUTO-ACC-WEB")
    _stock(client, owner_headers, product_id, "2")
    checkout = client.post(
        "/store/mily-zebra/checkout",
        headers={"Idempotency-Key": "auto-accounting-web-order"},
        json={
            "full_name": "Cliente web contable",
            "email": "web-accounting@example.com",
            "payment_method": "manual_transfer",
            "fulfillment_method": "pickup",
            "lines": [{"product_id": product_id, "quantity": "1"}],
        },
    )
    assert checkout.status_code == 201, checkout.text
    order_id = checkout.json()["id"]
    paid = client.post(
        f"/commerce/orders/{order_id}/mark-paid",
        headers=owner_headers,
        json={"external_reference": "BANK-AUTO-ACC-001"},
    )
    assert paid.status_code == 200, paid.text
    fulfilled = client.post(f"/commerce/orders/{order_id}/fulfill", headers=owner_headers)
    assert fulfilled.status_code == 200, fulfilled.text

    revenue = _entry_snapshot(f"ORDER-REVENUE:{order_id}")
    assert revenue["lines"]["1110"] == {"debit": Decimal("100.00"), "credit": Decimal("0")}
    assert revenue["lines"]["4000"] == {"debit": Decimal("0"), "credit": Decimal("100.00")}
    cogs = _entry_snapshot(f"ORDER-COGS:{order_id}")
    assert cogs["lines"]["5000"] == {"debit": Decimal("40.00"), "credit": Decimal("0")}
    assert cogs["lines"]["1300"] == {"debit": Decimal("0"), "credit": Decimal("40.00")}
