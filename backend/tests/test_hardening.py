from app.db import SessionLocal
from app.models import Branch, Tenant, User, UserRole
from app.security import hash_password


def test_bootstrap_requires_installation_code(client) -> None:
    payload = {
        "store_name": "Mily Zebra Secure",
        "store_slug": "mily-zebra-secure",
        "branch_name": "Roatán",
        "email": "secure@example.com",
        "full_name": "Owner",
        "password": "super-secure-password",
    }
    assert client.post("/bootstrap", json=payload).status_code == 403
    assert client.post(
        "/bootstrap",
        headers={"X-Bootstrap-Token": "wrong-bootstrap-token"},
        json=payload,
    ).status_code == 403
    created = client.post(
        "/bootstrap",
        headers={"X-Bootstrap-Token": "test-bootstrap-token"},
        json=payload,
    )
    assert created.status_code == 200, created.text
    assert client.post(
        "/bootstrap",
        headers={"X-Bootstrap-Token": "test-bootstrap-token"},
        json=payload,
    ).status_code == 409


def test_idempotency_key_rejects_different_sale_payload(client, owner_headers) -> None:
    product = client.post(
        "/products",
        headers=owner_headers,
        json={
            "sku": "IDEM-001",
            "name": "Producto idempotente",
            "sale_price": "100.00",
        },
    )
    assert product.status_code == 201
    product_id = product.json()["id"]
    stock = client.post(
        "/inventory/movements",
        headers=owner_headers,
        json={"product_id": product_id, "quantity_delta": "5", "reason": "seed"},
    )
    assert stock.status_code == 200
    assert client.post(
        "/cash/open",
        headers=owner_headers,
        json={"opening_amount": "0"},
    ).status_code == 201

    key = "same-key-different-body"
    first = client.post(
        "/sales",
        headers={**owner_headers, "Idempotency-Key": key},
        json={"payment_method": "cash", "lines": [{"product_id": product_id, "quantity": "1"}]},
    )
    assert first.status_code == 201, first.text
    conflict = client.post(
        "/sales",
        headers={**owner_headers, "Idempotency-Key": key},
        json={"payment_method": "cash", "lines": [{"product_id": product_id, "quantity": "2"}]},
    )
    assert conflict.status_code == 409, conflict.text


def test_core_branch_scope_rejects_other_tenant(client, owner_headers) -> None:
    product = client.post(
        "/products",
        headers=owner_headers,
        json={"sku": "SCOPE-001", "name": "Scope", "sale_price": "10.00"},
    )
    assert product.status_code == 201

    with SessionLocal() as db:
        tenant = Tenant(name="Otra empresa", slug="otra-empresa")
        db.add(tenant)
        db.flush()
        foreign_branch = Branch(tenant_id=tenant.id, code="OTH-01", name="Otra")
        db.add(foreign_branch)
        db.commit()
        foreign_branch_id = foreign_branch.id

    attempt = client.post(
        "/inventory/movements",
        headers=owner_headers,
        json={
            "branch_id": foreign_branch_id,
            "product_id": product.json()["id"],
            "quantity_delta": "1",
            "reason": "cross_tenant_attempt",
        },
    )
    assert attempt.status_code == 404


def test_duplicate_email_requires_tenant_qualified_login(client, owner_headers) -> None:
    with SessionLocal() as db:
        original = db.query(User).filter(User.email == "owner@example.com").one()
        original.password_hash = hash_password("same-email-password")
        tenant = Tenant(name="Segunda tienda", slug="segunda-tienda")
        db.add(tenant)
        db.flush()
        branch = Branch(tenant_id=tenant.id, code="SEG-01", name="Segunda")
        db.add(branch)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                branch_id=branch.id,
                email="owner@example.com",
                full_name="Owner segundo tenant",
                password_hash=hash_password("second-tenant-password"),
                role=UserRole.OWNER,
            )
        )
        db.commit()

    ambiguous = client.post(
        "/auth/login",
        data={"username": "owner@example.com", "password": "same-email-password"},
    )
    assert ambiguous.status_code == 409

    qualified = client.post(
        "/auth/login",
        data={
            "username": "segunda-tienda:owner@example.com",
            "password": "second-tenant-password",
        },
    )
    assert qualified.status_code == 200, qualified.text
    token = qualified.json()["access_token"]
    me = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "owner@example.com"
