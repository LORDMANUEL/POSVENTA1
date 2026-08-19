from decimal import Decimal

from sqlalchemy import select

from app.accounting_models import Account, JournalEntry, JournalLine
from app.commerce_models import OrderLine
from app.db import SessionLocal
from app.models import Product, SaleLine


def _journal_amount(reference: str, account_code: str, side: str) -> Decimal:
    with SessionLocal() as db:
        value = db.execute(
            select(JournalLine.debit, JournalLine.credit)
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .join(Account, Account.id == JournalLine.account_id)
            .where(JournalEntry.reference == reference, Account.code == account_code)
        ).one()
        return Decimal(value[0] if side == 'debit' else value[1])


def test_return_reverses_historical_sale_cost_not_current_product_cost(client, owner_headers) -> None:
    product = client.post(
        '/products',
        headers=owner_headers,
        json={
            'sku': 'HIST-COST-001',
            'name': 'Producto costo histórico',
            'unit_cost': '100.00',
            'sale_price': '250.00',
        },
    )
    assert product.status_code == 201
    product_id = product.json()['id']
    assert client.post(
        '/inventory/movements',
        headers=owner_headers,
        json={'product_id': product_id, 'quantity_delta': '2', 'reason': 'opening_stock'},
    ).status_code == 200
    assert client.post('/cash/open', headers=owner_headers, json={'opening_amount': '0'}).status_code == 201

    sale = client.post(
        '/sales',
        headers={**owner_headers, 'Idempotency-Key': 'historical-cost-sale'},
        json={'payment_method': 'cash', 'lines': [{'product_id': product_id, 'quantity': '1'}]},
    )
    assert sale.status_code == 201
    sale_id = sale.json()['id']

    with SessionLocal() as db:
        line = db.scalar(select(SaleLine).where(SaleLine.sale_id == sale_id))
        assert line is not None
        assert Decimal(line.unit_cost) == Decimal('100.00')
        row = db.scalar(select(Product).where(Product.id == product_id))
        row.unit_cost = Decimal('175.00')
        db.commit()

    detail = client.get(f'/post-sales/sales/{sale_id}', headers=owner_headers).json()
    sale_line_id = detail['lines'][0]['sale_line_id']
    returned = client.post(
        '/post-sales/returns',
        headers={**owner_headers, 'Idempotency-Key': 'historical-cost-return'},
        json={
            'sale_id': sale_id,
            'reason': 'Cambio después de cambio de costo',
            'lines': [{'sale_line_id': sale_line_id, 'quantity': '1'}],
        },
    )
    assert returned.status_code == 201, returned.text

    assert _journal_amount(f'SALE:{sale_id}', '5000', 'debit') == Decimal('100.00')
    assert _journal_amount(f"RETURN:{returned.json()['id']}", '5000', 'credit') == Decimal('100.00')


def test_ecommerce_fulfillment_uses_checkout_cost_snapshot(client, owner_headers) -> None:
    product = client.post(
        '/products',
        headers=owner_headers,
        json={
            'sku': 'HIST-WEB-001',
            'name': 'Producto web costo histórico',
            'unit_cost': '80.00',
            'sale_price': '200.00',
        },
    )
    assert product.status_code == 201
    product_id = product.json()['id']
    assert client.post(
        '/inventory/movements',
        headers=owner_headers,
        json={'product_id': product_id, 'quantity_delta': '2', 'reason': 'opening_stock'},
    ).status_code == 200

    checkout = client.post(
        '/store/mily-zebra/checkout',
        headers={'Idempotency-Key': 'historical-web-order'},
        json={
            'full_name': 'Cliente histórico',
            'email': 'historical.web@example.com',
            'payment_method': 'manual_transfer',
            'fulfillment_method': 'pickup',
            'lines': [{'product_id': product_id, 'quantity': '1'}],
        },
    )
    assert checkout.status_code == 201, checkout.text
    order_id = checkout.json()['id']

    with SessionLocal() as db:
        line = db.scalar(select(OrderLine).where(OrderLine.order_id == order_id))
        assert line is not None
        assert Decimal(line.unit_cost) == Decimal('80.00')
        row = db.scalar(select(Product).where(Product.id == product_id))
        row.unit_cost = Decimal('140.00')
        db.commit()

    paid = client.post(
        f'/commerce/orders/{order_id}/mark-paid',
        headers=owner_headers,
        json={'external_reference': 'HIST-WEB-PAY-001'},
    )
    assert paid.status_code == 200, paid.text
    fulfilled = client.post(
        f'/commerce/orders/{order_id}/fulfill',
        headers=owner_headers,
    )
    assert fulfilled.status_code == 200, fulfilled.text

    assert _journal_amount(f'ORDER-COGS:{order_id}', '5000', 'debit') == Decimal('80.00')
