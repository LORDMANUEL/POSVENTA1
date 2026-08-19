def enable(client, headers, key: str):
    response = client.put(f"/admin/modules/{key}?enabled=true", headers=headers)
    assert response.status_code == 200, response.text


def test_bank_reconciliation_matches_receivable_payment(client, owner_headers):
    enable(client, owner_headers, "accounting")
    enable(client, owner_headers, "receivables")
    enable(client, owner_headers, "banking")

    customer = client.post(
        "/ops/customers",
        headers=owner_headers,
        json={"full_name": "Cliente Banco", "email": "bank@example.com", "phone": "99990000", "notes": ""},
    )
    assert customer.status_code == 201, customer.text
    customer_id = customer.json()["id"]

    receivable = client.post(
        "/finance/receivables",
        headers=owner_headers,
        json={"party_id": customer_id, "reference": "CXC-BANK-001", "description": "Venta crédito", "amount": "750.00", "due_date": None},
    )
    assert receivable.status_code == 201, receivable.text
    receivable_id = receivable.json()["id"]

    payment = client.post(
        f"/finance/receivables/{receivable_id}/payments",
        headers=owner_headers,
        json={"amount": "750.00", "method": "bank_transfer", "reference": "TRX-CLIENTE-001"},
    )
    assert payment.status_code == 201, payment.text
    payment_id = payment.json()["id"]

    account = client.post(
        "/finance/banking/accounts",
        headers=owner_headers,
        json={"name": "Cuenta principal", "bank_name": "Banco Demo", "currency": "HNL", "account_last4": "1234", "ledger_account_id": None},
    )
    assert account.status_code == 201, account.text
    account_id = account.json()["id"]

    transaction = client.post(
        f"/finance/banking/accounts/{account_id}/transactions",
        headers=owner_headers,
        json={"transaction_date": "2026-08-19", "description": "Transferencia cliente", "amount": "750.00", "external_reference": "BANK-0001"},
    )
    assert transaction.status_code == 201, transaction.text
    transaction_id = transaction.json()["id"]

    unmatched = client.get("/finance/reconciliation/unmatched", headers=owner_headers)
    assert unmatched.status_code == 200
    assert transaction_id in {row["id"] for row in unmatched.json()}

    suggestions = client.get(f"/finance/reconciliation/{transaction_id}/suggestions", headers=owner_headers)
    assert suggestions.status_code == 200
    assert any(row["matched_id"] == payment_id and row["matched_type"] == "receivable_payment" for row in suggestions.json())

    matched = client.post(
        f"/finance/reconciliation/{transaction_id}/match",
        headers=owner_headers,
        json={"matched_type": "receivable_payment", "matched_id": payment_id},
    )
    assert matched.status_code == 200, matched.text
    assert matched.json()["status"] == "matched"

    idempotent = client.post(
        f"/finance/reconciliation/{transaction_id}/match",
        headers=owner_headers,
        json={"matched_type": "receivable_payment", "matched_id": payment_id},
    )
    assert idempotent.status_code == 200

    unmatch = client.post(f"/finance/reconciliation/{transaction_id}/unmatch", headers=owner_headers)
    assert unmatch.status_code == 200
    assert unmatch.json()["status"] == "unmatched"
