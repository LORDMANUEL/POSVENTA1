def test_public_checkout_reserves_tracks_and_fulfills_stock(client, owner_headers) -> None:
    product = client.post(
        "/products",
        headers=owner_headers,
        json={
            "sku": "MZ-WEB-001",
            "name": "Blusa Island Web",
            "category": "Island Mood",
            "unit_cost": "200.00",
            "sale_price": "499.00",
        },
    )
    assert product.status_code == 201
    product_id = product.json()["id"]
    assert client.post(
        "/inventory/movements",
        headers=owner_headers,
        json={"product_id": product_id, "quantity_delta": "4", "reason": "opening_stock"},
    ).status_code == 200

    catalog = client.get("/store/mily-zebra/catalog")
    assert catalog.status_code == 200
    assert catalog.json()["products"][0]["id"] == product_id

    checkout = client.post(
        "/store/mily-zebra/checkout",
        headers={"Idempotency-Key": "web-order-0001"},
        json={
            "full_name": "Cliente Web",
            "email": "cliente@example.com",
            "phone": "+50422222222",
            "payment_method": "manual_transfer",
            "fulfillment_method": "pickup",
            "lines": [{"product_id": product_id, "quantity": "2"}],
        },
    )
    assert checkout.status_code == 201
    body = checkout.json()
    assert body["status"] == "pending_payment"
    assert body["total"] == "998.00"
    assert body["tracking_token"]

    repeated = client.post(
        "/store/mily-zebra/checkout",
        headers={"Idempotency-Key": "web-order-0001"},
        json={
            "full_name": "Cliente Web",
            "email": "cliente@example.com",
            "payment_method": "manual_transfer",
            "lines": [{"product_id": product_id, "quantity": "2"}],
        },
    )
    assert repeated.status_code == 201
    assert repeated.json()["id"] == body["id"]
    assert repeated.json()["tracking_token"] == body["tracking_token"]

    blocked = client.post(
        "/store/mily-zebra/checkout",
        headers={"Idempotency-Key": "web-order-0002"},
        json={
            "full_name": "Otra Cliente",
            "payment_method": "cash_on_delivery",
            "lines": [{"product_id": product_id, "quantity": "3"}],
        },
    )
    assert blocked.status_code == 409

    tracked = client.get(
        f"/store/mily-zebra/orders/{body['id']}/track",
        params={"token": body["tracking_token"]},
    )
    assert tracked.status_code == 200
    assert tracked.json()["status"] == "pending_payment"

    paid = client.post(
        f"/commerce/orders/{body['id']}/mark-paid",
        headers=owner_headers,
        json={"external_reference": "BANK-TEST-001"},
    )
    assert paid.status_code == 200
    assert paid.json()["status"] == "confirmed"

    fulfilled = client.post(f"/commerce/orders/{body['id']}/fulfill", headers=owner_headers)
    assert fulfilled.status_code == 200
    assert fulfilled.json()["status"] == "fulfilled"

    inventory = client.get("/inventory", headers=owner_headers).json()
    row = next(item for item in inventory if item["product_id"] == product_id)
    assert row["quantity"] == "2.000"
