def test_owner_can_query_tenant_scoped_audit_events(client, owner_headers) -> None:
    product = client.post(
        "/products",
        headers=owner_headers,
        json={
            "sku": "AUDIT-001",
            "name": "Producto auditado",
            "unit_cost": "10.00",
            "sale_price": "25.00",
        },
    )
    assert product.status_code == 201

    events = client.get(
        "/audit/events",
        headers=owner_headers,
        params={"action": "product.created", "limit": 25},
    )
    assert events.status_code == 200, events.text
    rows = events.json()
    assert any(
        row["action"] == "product.created"
        and row["entity_type"] == "product"
        and row["entity_id"] == product.json()["id"]
        for row in rows
    )
    assert all("tenant_id" not in row for row in rows)
