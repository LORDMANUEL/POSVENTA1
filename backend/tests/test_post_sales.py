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

    opened = client.post("/cash/open", headers=owner_headers, json={"opening_amount": "300.00"})
    assert opened.status_code == 201
    cash_session_id = opened.json()["id"]

    sale = client.post(
        "/sales",
        headers={**owner_headers, "Idempotency-Key": "return-sale-0001"},
        json={"payment_method": "cash", "lines": [{"product_id": product_id, "quantity": "3"}]},
    )
    assert sale.status_code == 201
    sale_id = sale.json()["id"]

    recent = client.get("/post-sales/sales", headers=owner_headers)
    assert recent.status_code == 200
    assert any(item["id"] == sale_id for item in recent.json())

    detail = client.get(f"/post-sales/sales/{sale_id}", headers=owner_headers)
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["id"] == sale_id
    assert detail_body["payment_method"] == "cash"
    assert len(detail_body["lines"]) == 1
    assert detail_body["lines"][0]["product_id"] == product_id
    assert detail_body["lines"][0]["sku"] == "MZ-RET-001"
    assert detail_body["lines"][0]["quantity_sold"] == "3.000"
    assert detail_body["lines"][0]["quantity_returned"] == "0.000"
    assert detail_body["lines"][0]["quantity_returnable"] == "3.000"
    sale_line_id = detail_body["lines"][0]["sale_line_id"]

    before_return = client.get(f"/cash/{cash_session_id}/summary", headers=owner_headers)
    assert before_return.status_code == 200
    assert before_return.json()["expected_amount"] == "2397.00"

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

    after_return = client.get(f"/cash/{cash_session_id}/summary", headers=owner_headers)
    assert after_return.status_code == 200
    assert after_return.json()["expected_amount"] == "1698.00"
    refund_movements = [
        movement for movement in after_return.json()["movements"]
        if movement.get("reference_type") == "refund"
    ]
    assert len(refund_movements) == 1
    assert refund_movements[0]["amount"] == "-699.00"

    detail_after = client.get(f"/post-sales/sales/{sale_id}", headers=owner_headers)
    assert detail_after.status_code == 200
    assert detail_after.json()["lines"][0]["quantity_returned"] == "1.000"
    assert detail_after.json()["lines"][0]["quantity_returnable"] == "2.000"

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


def test_cash_return_requires_open_cash_session(client, owner_headers) -> None:
    product = client.post(
        "/products",
        headers=owner_headers,
        json={"sku": "MZ-RET-CLOSE", "name": "Producto refund", "unit_cost": "10", "sale_price": "100"},
    )
    product_id = product.json()["id"]
    client.post(
        "/inventory/movements",
        headers=owner_headers,
        json={"product_id": product_id, "quantity_delta": "2", "reason": "opening_stock"},
    )
    opened = client.post("/cash/open", headers=owner_headers, json={"opening_amount": "0"})
    sale = client.post(
        "/sales",
        headers={**owner_headers, "Idempotency-Key": "return-closed-cash"},
        json={"payment_method": "cash", "lines": [{"product_id": product_id, "quantity": "1"}]},
    )
    sale_id = sale.json()["id"]
    line_id = client.get(f"/post-sales/sales/{sale_id}", headers=owner_headers).json()["lines"][0]["sale_line_id"]
    close = client.post(
        f"/cash/{opened.json()['id']}/close",
        headers=owner_headers,
        json={"closing_amount": "100"},
    )
    assert close.status_code == 200

    refused = client.post(
        "/post-sales/returns",
        headers=owner_headers,
        json={"sale_id": sale_id, "reason": "Caja cerrada", "lines": [{"sale_line_id": line_id, "quantity": "1"}]},
    )
    assert refused.status_code == 409

    stock = client.get("/inventory", headers=owner_headers).json()
    row = next(item for item in stock if item["product_id"] == product_id)
    assert row["quantity"] == "1.000"
