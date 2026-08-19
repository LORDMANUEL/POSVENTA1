def enable(client, headers, key: str) -> None:
    response = client.put(f"/admin/modules/{key}?enabled=true", headers=headers)
    assert response.status_code == 200, response.text


def test_configurable_fiscal_sequence_is_idempotent(client, owner_headers) -> None:
    enable(client, owner_headers, "accounting")
    enable(client, owner_headers, "fiscal")
    branch_id = client.get("/me", headers=owner_headers).json()["branch_id"]

    fiscal_range = client.post(
        "/fiscal/ranges",
        headers=owner_headers,
        json={
            "branch_id": branch_id,
            "document_type": "invoice",
            "cai": "TEST-CAI-NOT-FOR-PRODUCTION",
            "prefix": "RTN-",
            "range_start": 1,
            "range_end": 2,
            "expires_on": "2099-12-31",
        },
    )
    assert fiscal_range.status_code == 201

    issued = client.post(
        "/fiscal/documents",
        headers=owner_headers,
        json={
            "branch_id": branch_id,
            "document_type": "invoice",
            "source_type": "sale",
            "source_id": "sale-fiscal-test-1",
            "payload": {"total": "100.00"},
        },
    )
    assert issued.status_code == 201
    assert issued.json()["document_number"] == "RTN-00000001"

    repeated = client.post(
        "/fiscal/documents",
        headers=owner_headers,
        json={
            "branch_id": branch_id,
            "document_type": "invoice",
            "source_type": "sale",
            "source_id": "sale-fiscal-test-1",
            "payload": {"total": "100.00"},
        },
    )
    assert repeated.status_code == 201
    assert repeated.json()["document_number"] == issued.json()["document_number"]


def test_rag_and_ai_remain_grounded_without_model(client, owner_headers) -> None:
    enable(client, owner_headers, "rag")
    enable(client, owner_headers, "ai")

    document = client.post(
        "/rag/documents",
        headers=owner_headers,
        json={
            "source_key": "policy-returns",
            "title": "Política de cambios",
            "source_type": "policy",
            "content": "Los cambios de talla requieren comprobante de compra y revisión del estado de la prenda.",
        },
    )
    assert document.status_code == 201

    search = client.post(
        "/rag/search",
        headers=owner_headers,
        json={"question": "¿Qué necesito para un cambio de talla?", "limit": 3},
    )
    assert search.status_code == 200
    assert search.json()["sources"]
    assert search.json()["sources"][0]["source_key"] == "policy-returns"

    answer = client.post(
        "/ai/ask",
        headers=owner_headers,
        json={"question": "¿Qué necesito para un cambio de talla?", "limit": 3},
    )
    assert answer.status_code == 200
    assert answer.json()["mode"] in {"retrieval_only", "ollama_rag"}
    assert answer.json()["sources"][0]["source_key"] == "policy-returns"

    no_context = client.post(
        "/ai/ask",
        headers=owner_headers,
        json={"question": "¿Cuál es la órbita de Neptuno?", "limit": 3},
    )
    assert no_context.status_code == 200
    assert no_context.json()["mode"] == "no_context"
