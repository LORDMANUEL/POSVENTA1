def test_stock_count_replenishment_and_label_queue(client, owner_headers) -> None:
    product = client.post(
        "/products",
        headers=owner_headers,
        json={
            "sku": "COUNT-001",
            "barcode": "740000000001",
            "name": "Producto Conteo",
            "category": "Mily Basics",
            "unit_cost": "100.00",
            "sale_price": "250.00",
        },
    )
    assert product.status_code == 201
    product_id = product.json()["id"]

    movement = client.post(
        "/inventory/movements",
        headers=owner_headers,
        json={"product_id": product_id, "quantity_delta": "5", "reason": "opening_stock"},
    )
    assert movement.status_code == 200

    count = client.post(
        "/inventory-advanced/counts",
        headers=owner_headers,
        json={"note": "Conteo físico", "lines": [{"product_id": product_id, "counted_quantity": "3"}]},
    )
    assert count.status_code == 201

    approved = client.post(
        f"/inventory-advanced/counts/{count.json()['id']}/approve",
        headers=owner_headers,
    )
    assert approved.status_code == 200
    assert approved.json()["adjustments"] == 1

    stock = client.get("/inventory", headers=owner_headers).json()
    row = next(item for item in stock if item["product_id"] == product_id)
    assert row["quantity"] == "3.000"

    rule = client.put(
        "/inventory-advanced/replenishment-rules",
        headers=owner_headers,
        json={"product_id": product_id, "min_quantity": "3", "target_quantity": "10"},
    )
    assert rule.status_code == 200

    suggestions = client.get("/inventory-advanced/replenishment-suggestions", headers=owner_headers)
    assert suggestions.status_code == 200
    suggestion = next(item for item in suggestions.json() if item["product_id"] == product_id)
    assert suggestion["suggested_quantity"] == "7.000"

    label = client.post(
        "/inventory-advanced/labels",
        headers=owner_headers,
        json={"product_id": product_id, "copies": 2, "include_qr": True},
    )
    assert label.status_code == 201
    assert label.json()["protocol"] == "zpl"
