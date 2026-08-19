def test_health(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_bootstrap_login_and_product_flow(client, owner_headers) -> None:
    created = client.post(
        "/products",
        headers=owner_headers,
        json={
            "sku": "MZ-001",
            "barcode": "750000000001",
            "name": "Blusa Rosa Essential",
            "description": "Prenda de prueba",
            "category": "Mily Basics",
            "size": "M",
            "color": "Rosa",
            "unit_cost": "220.00",
            "sale_price": "449.00",
        },
    )
    assert created.status_code == 201
    product_id = created.json()["id"]

    moved = client.post(
        "/inventory/movements",
        headers=owner_headers,
        json={"product_id": product_id, "quantity_delta": "5", "reason": "opening_stock"},
    )
    assert moved.status_code == 200
    assert moved.json()["quantity"] == "5.000"

    sold = client.post(
        "/sales",
        headers={**owner_headers, "Idempotency-Key": "sale-test-0001"},
        json={"payment_method": "cash", "lines": [{"product_id": product_id, "quantity": "2"}]},
    )
    assert sold.status_code == 201
    assert sold.json()["total"] == "898.00"

    repeated = client.post(
        "/sales",
        headers={**owner_headers, "Idempotency-Key": "sale-test-0001"},
        json={"payment_method": "cash", "lines": [{"product_id": product_id, "quantity": "2"}]},
    )
    assert repeated.status_code == 201
    assert repeated.json()["id"] == sold.json()["id"]

    stock = client.get("/inventory", headers=owner_headers)
    assert stock.status_code == 200
    assert stock.json()[0]["quantity"] == "3.000"


def test_bootstrap_is_one_shot(client, owner_headers) -> None:
    second = client.post(
        "/bootstrap",
        json={
            "store_name": "Otra",
            "branch_name": "Otra",
            "email": "other@example.com",
            "full_name": "Other Owner",
            "password": "another-secure-password",
        },
    )
    assert second.status_code == 409
