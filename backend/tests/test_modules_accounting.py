def test_module_registry_and_accounting_flow(client, owner_headers) -> None:
    modules = client.get("/admin/modules", headers=owner_headers)
    assert modules.status_code == 200
    by_key = {row["key"]: row for row in modules.json()}
    assert by_key["catalog"]["enabled"] is True
    assert by_key["accounting"]["enabled"] is False

    enable_accounting = client.put("/admin/modules/accounting?enabled=true", headers=owner_headers)
    assert enable_accounting.status_code == 200
    assert enable_accounting.json() == {"key": "accounting", "enabled": True}

    cash = client.post(
        "/accounting/accounts",
        headers=owner_headers,
        json={"code": "1101", "name": "Caja general", "account_type": "asset"},
    )
    assert cash.status_code == 201
    sales = client.post(
        "/accounting/accounts",
        headers=owner_headers,
        json={"code": "4101", "name": "Ventas", "account_type": "income"},
    )
    assert sales.status_code == 201

    unbalanced = client.post(
        "/accounting/entries",
        headers=owner_headers,
        json={
            "reference": "TEST-UNBALANCED",
            "description": "Debe fallar",
            "lines": [
                {"account_id": cash.json()["id"], "debit": "100.00", "credit": "0"},
                {"account_id": sales.json()["id"], "debit": "0", "credit": "90.00"},
            ],
        },
    )
    assert unbalanced.status_code == 422

    entry = client.post(
        "/accounting/entries",
        headers=owner_headers,
        json={
            "reference": "TEST-SALE-001",
            "description": "Venta de prueba",
            "source_type": "test",
            "lines": [
                {"account_id": cash.json()["id"], "debit": "100.00", "credit": "0"},
                {"account_id": sales.json()["id"], "debit": "0", "credit": "100.00"},
            ],
        },
    )
    assert entry.status_code == 201
    posted = client.post(f"/accounting/entries/{entry.json()['id']}/post", headers=owner_headers)
    assert posted.status_code == 200
    assert posted.json()["status"] == "posted"

    trial = client.get("/accounting/trial-balance", headers=owner_headers)
    assert trial.status_code == 200
    rows = {row["code"]: row for row in trial.json()}
    assert rows["1101"]["balance"] == "100.00"
    assert rows["4101"]["balance"] == "-100.00"

    result = client.get("/accounting/income-statement", headers=owner_headers)
    assert result.status_code == 200
    assert result.json()["total_income"] == "100.00"
    assert result.json()["total_expenses"] == "0.00"
    assert result.json()["net_income"] == "100.00"

    balance = client.get("/accounting/balance-sheet", headers=owner_headers)
    assert balance.status_code == 200
    assert balance.json()["total_assets"] == "100.00"
    assert balance.json()["current_result"] == "100.00"
    assert balance.json()["liabilities_plus_equity"] == "100.00"
    assert balance.json()["difference"] == "0.00"
