from app.config import get_settings


def test_payments_module_runs_end_to_end_only_in_sandbox_mode(
    client,
    owner_headers,
    monkeypatch,
) -> None:
    product = client.post(
        "/products",
        headers=owner_headers,
        json={
            "sku": "PAY-SBX-001",
            "name": "Producto pago sandbox",
            "unit_cost": "20.00",
            "sale_price": "75.00",
        },
    )
    assert product.status_code == 201
    product_id = product.json()["id"]
    assert client.post(
        "/inventory/movements",
        headers=owner_headers,
        json={"product_id": product_id, "quantity_delta": "2", "reason": "sandbox_seed"},
    ).status_code == 200

    order = client.post(
        "/store/mily-zebra/checkout",
        headers={"Idempotency-Key": "payment-sandbox-order"},
        json={
            "full_name": "Cliente Sandbox",
            "email": "payments-sandbox@example.com",
            "payment_method": "manual_transfer",
            "fulfillment_method": "pickup",
            "lines": [{"product_id": product_id, "quantity": "1"}],
        },
    )
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]

    blocked = client.get("/payments/status", headers=owner_headers)
    assert blocked.status_code == 403

    monkeypatch.setenv("MZ_SANDBOX_EXTERNAL_MODULES", "payments")
    get_settings.cache_clear()
    try:
        enabled = client.put(
            "/admin/modules/payments",
            params={"enabled": "true"},
            headers=owner_headers,
        )
        assert enabled.status_code == 200, enabled.text
        assert enabled.json()["external_mode"] == "sandbox"

        status = client.get("/payments/status", headers=owner_headers)
        assert status.status_code == 200, status.text
        assert status.json() == {"provider": "sandbox", "mode": "sandbox"}

        intent = client.post(
            f"/payments/orders/{order_id}/intent",
            headers={**owner_headers, "Idempotency-Key": "payment-intent-0001"},
        )
        assert intent.status_code == 201, intent.text
        body = intent.json()
        assert body["provider"] == "sandbox"
        assert body["status"] == "pending"
        assert body["amount"] == "75.00"
        assert body["reference"].startswith("mz_sandbox_")

        replay = client.post(
            f"/payments/orders/{order_id}/intent",
            headers={**owner_headers, "Idempotency-Key": "payment-intent-0001"},
        )
        assert replay.status_code == 201
        assert replay.json() == body

        confirmed = client.post(
            f"/payments/orders/{order_id}/sandbox-confirm",
            headers=owner_headers,
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["payment_status"] == "paid"
        assert confirmed.json()["order_status"] == "confirmed"
    finally:
        monkeypatch.delenv("MZ_SANDBOX_EXTERNAL_MODULES", raising=False)
        get_settings.cache_clear()
