def test_partial_return_restores_stock_and_prevents_over_return(client, owner_headers) -> None:
    product = client.post(
        "/products",
        headers=owner_headers,
        json={
            "sku": "MZ-RET-001",
            "name": "Vestido Return Test",
            "category": "Pink Vibes",
            "unit_cost": "250.00",
            "sale_price": "699.00",
        },
    )
    assert product.status_code == 201
    product_id = product.json()["id"]

    assert client.post(
        "/inventory/movements",
        headers=owner_headers,
        json={"product_id": product_id, "quantity_delta": "5", "reason": "opening_stock"},
    ).status_code == 200

    sale = client.post(
        "/sales",
        headers={**owner_headers, "Idempotency-Key": "return-sale-0001"},
        json={"payment_method": "cash", "lines": [{"product_id": product_id, "quantity": "3"}]},
    )
    assert sale.status_code == 201
    sale_id = sale.json()["id"]

    from app.db import SessionLocal
    from app.models import SaleLine
    from sqlalchemy import select

    with SessionLocal() as db:
        sale_line = db.scalar(select(SaleLine).where(SaleLine.sale_id == sale_id))
        sale_line_id = sale_line.id

    returned = client.post(
        "/post-sales/returns",
        headers=owner_headers,
        json={
            "sale_id": sale_id,
            "reason": "Cambio de talla",
            "lines": [{"sale_line_id": sale_line_id, "quantity": "1"}],
        },
    )
    assert returned.status_code == 201
    assert returned.json()["total"] == "699.00"
    assert returned.json()["refund"]["status"] == "completed"

    inventory = client.get("/inventory", headers=owner_headers).json()
    row = next(item for item in inventory if item["product_id"] == product_id)
    assert row["quantity"] == "3.000"

    too_many = client.post(
        "/post-sales/returns",
        headers=owner_headers,
        json={
            "sale_id": sale_id,
            "reason": "Intento inválido",
            "lines": [{"sale_line_id": sale_line_id, "quantity": "3"}],
        },
    )
    assert too_many.status_code == 409
