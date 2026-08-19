def enable(client, headers, key: str) -> None:
    response = client.put(f"/admin/modules/{key}?enabled=true", headers=headers)
    assert response.status_code == 200, response.text


def test_receivables_payables_and_banking_are_modular(client, owner_headers) -> None:
    # Internal finance modules are operational by default on a fresh stable install.
    assert client.get("/finance/receivables", headers=owner_headers).status_code == 200

    # A tenant can still disable an optional module explicitly; its API then fails closed.
    disabled = client.put("/admin/modules/receivables?enabled=false", headers=owner_headers)
    assert disabled.status_code == 200
    assert client.get("/finance/receivables", headers=owner_headers).status_code == 403
    enable(client, owner_headers, "receivables")

    customer = client.post(
        "/ops/customers",
        headers=owner_headers,
        json={"full_name": "Cliente Crédito", "email": "credito@example.com"},
    )
    assert customer.status_code == 201
    supplier = client.post(
        "/ops/suppliers",
        headers=owner_headers,
        json={"name": "Proveedor Crédito"},
    )
    assert supplier.status_code == 201

    receivable = client.post(
        "/finance/receivables",
        headers=owner_headers,
        json={"party_id": customer.json()["id"], "reference": "CXC-001", "amount": "500.00"},
    )
    assert receivable.status_code == 201
    partial = client.post(
        f"/finance/receivables/{receivable.json()['id']}/payments",
        headers=owner_headers,
        json={"amount": "200.00", "method": "cash"},
    )
    assert partial.status_code == 201
    assert partial.json()["balance"] == "300.00"
    assert partial.json()["status"] == "partial"

    payable = client.post(
        "/finance/payables",
        headers=owner_headers,
        json={"party_id": supplier.json()["id"], "reference": "CXP-001", "amount": "800.00"},
    )
    assert payable.status_code == 201
    paid = client.post(
        f"/finance/payables/{payable.json()['id']}/payments",
        headers=owner_headers,
        json={"amount": "800.00", "method": "transfer", "reference": "BANK-001"},
    )
    assert paid.status_code == 201
    assert paid.json()["balance"] == "0.00"
    assert paid.json()["status"] == "paid"

    bank = client.post(
        "/finance/banking/accounts",
        headers=owner_headers,
        json={"name": "Cuenta principal", "bank_name": "Banco de prueba", "currency": "HNL", "account_last4": "1234"},
    )
    assert bank.status_code == 201
    tx = client.post(
        f"/finance/banking/accounts/{bank.json()['id']}/transactions",
        headers=owner_headers,
        json={"transaction_date": "2026-08-18", "description": "Depósito", "amount": "200.00", "external_reference": "MOV-001"},
    )
    assert tx.status_code == 201
    assert tx.json()["reconciliation_status"] == "unmatched"

    duplicate = client.post(
        f"/finance/banking/accounts/{bank.json()['id']}/transactions",
        headers=owner_headers,
        json={"transaction_date": "2026-08-18", "description": "Duplicado", "amount": "200.00", "external_reference": "MOV-001"},
    )
    assert duplicate.status_code == 409
