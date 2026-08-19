import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["AUTO_CREATE_SCHEMA"] = "true"

from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_bootstrap_login_and_product_flow() -> None:
    with TestClient(app) as client:
        bootstrap = client.post(
            "/bootstrap",
            json={
                "store_name": "Mily Zebra",
                "branch_name": "Roatán",
                "email": "owner@example.com",
                "full_name": "Owner",
                "password": "super-secure-password",
            },
        )
        assert bootstrap.status_code == 200
        token = bootstrap.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        created = client.post(
            "/products",
            headers=headers,
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
            headers=headers,
            json={"product_id": product_id, "quantity_delta": "5", "reason": "opening_stock"},
        )
        assert moved.status_code == 200
        assert moved.json()["quantity"] == "5.000"

        sold = client.post(
            "/sales",
            headers={**headers, "Idempotency-Key": "sale-test-0001"},
            json={"payment_method": "cash", "lines": [{"product_id": product_id, "quantity": "2"}]},
        )
        assert sold.status_code == 201
        assert sold.json()["total"] == "898.00"

        # Same idempotency key returns the same transaction and must not deduct twice.
        repeated = client.post(
            "/sales",
            headers={**headers, "Idempotency-Key": "sale-test-0001"},
            json={"payment_method": "cash", "lines": [{"product_id": product_id, "quantity": "2"}]},
        )
        assert repeated.status_code == 201
        assert repeated.json()["id"] == sold.json()["id"]

        stock = client.get("/inventory", headers=headers)
        assert stock.status_code == 200
        assert stock.json()[0]["quantity"] == "3.000"
