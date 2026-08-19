def test_returns_module_can_be_disabled_fail_closed(client, owner_headers) -> None:
    enabled = client.get("/post-sales/sales", headers=owner_headers)
    assert enabled.status_code == 200

    disabled = client.put("/admin/modules/returns?enabled=false", headers=owner_headers)
    assert disabled.status_code == 200
    assert disabled.json() == {"key": "returns", "enabled": False}

    assert client.get("/post-sales/sales", headers=owner_headers).status_code == 403
    assert client.get("/post-sales/returns", headers=owner_headers).status_code == 403

    restored = client.put("/admin/modules/returns?enabled=true", headers=owner_headers)
    assert restored.status_code == 200
    assert client.get("/post-sales/sales", headers=owner_headers).status_code == 200
