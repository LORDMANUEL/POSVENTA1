def enable_module(client, headers, key: str) -> None:
    response = client.put(f"/admin/modules/{key}?enabled=true", headers=headers)
    assert response.status_code == 200, response.text


def create_product(client, headers, sku="MZ-OPS-001"):
    response = client.post(
        "/products",
        headers=headers,
        json={
            "sku": sku,
            "name": "Producto operativo",
            "category": "Mily Basics",
            "unit_cost": "100.00",
            "sale_price": "249.00",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_optional_ops_are_fail_closed(client, owner_headers) -> None:
    assert client.get("/ops/suppliers", headers=owner_headers).status_code == 403
    assert client.get("/ops/deliveries", headers=owner_headers).status_code == 403


def test_purchase_receipt_and_transfer_between_branches(client, owner_headers) -> None:
    enable_module(client, owner_headers, "purchasing")
    branches = client.get("/admin/branches", headers=owner_headers).json()
    origin_id = branches[0]["id"]

    destination = client.post(
        "/admin/branches",
        headers=owner_headers,
        json={"code": "SPS-01", "name": "San Pedro Sula"},
    )
    assert destination.status_code == 201
    destination_id = destination.json()["id"]

    product_id = create_product(client, owner_headers)
    supplier = client.post(
        "/ops/suppliers",
        headers=owner_headers,
        json={"name": "Proveedor Demo", "phone": "+50400000000"},
    )
    assert supplier.status_code == 201

    purchase = client.post(
        "/ops/purchases",
        headers=owner_headers,
        json={
            "supplier_id": supplier.json()["id"],
            "branch_id": origin_id,
            "lines": [{"product_id": product_id, "quantity": "10", "unit_cost": "100.00"}],
        },
    )
    assert purchase.status_code == 201
    received = client.post(f"/ops/purchases/{purchase.json()['id']}/receive", headers=owner_headers)
    assert received.status_code == 200
    assert received.json()["status"] == "received"

    transfer = client.post(
        "/ops/transfers",
        headers=owner_headers,
        json={
            "from_branch_id": origin_id,
            "to_branch_id": destination_id,
            "lines": [{"product_id": product_id, "quantity": "3"}],
        },
    )
    assert transfer.status_code == 201
    transfer_id = transfer.json()["id"]
    assert client.post(f"/ops/transfers/{transfer_id}/ship", headers=owner_headers).json()["status"] == "shipped"
    assert client.post(f"/ops/transfers/{transfer_id}/receive", headers=owner_headers).json()["status"] == "received"

    inventory = client.get("/inventory", headers=owner_headers).json()
    by_branch = {row["branch_id"]: row["quantity"] for row in inventory if row["product_id"] == product_id}
    assert by_branch[origin_id] == "7.000"
    assert by_branch[destination_id] == "3.000"


def test_driver_only_updates_assigned_delivery(client, owner_headers) -> None:
    enable_module(client, owner_headers, "delivery")
    branch_id = client.get("/admin/branches", headers=owner_headers).json()[0]["id"]
    driver = client.post(
        "/ops/users",
        headers=owner_headers,
        json={
            "email": "driver@example.com",
            "full_name": "Driver Mily",
            "password": "driver-secure-password",
            "role": "driver",
            "branch_id": branch_id,
        },
    )
    assert driver.status_code == 201

    customer = client.post(
        "/ops/customers",
        headers=owner_headers,
        json={"full_name": "Cliente Roatán", "phone": "+50411111111"},
    )
    assert customer.status_code == 201

    delivery = client.post(
        "/ops/deliveries",
        headers=owner_headers,
        json={
            "branch_id": branch_id,
            "customer_id": customer.json()["id"],
            "driver_user_id": driver.json()["id"],
            "address_text": "West End, Roatán",
        },
    )
    assert delivery.status_code == 201
    assert delivery.json()["status"] == "assigned"

    login = client.post(
        "/auth/login",
        data={"username": "driver@example.com", "password": "driver-secure-password"},
    )
    assert login.status_code == 200
    driver_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assigned = client.get("/ops/deliveries", headers=driver_headers)
    assert assigned.status_code == 200
    assert len(assigned.json()) == 1

    delivered = client.post(
        f"/ops/deliveries/{delivery.json()['id']}/status",
        headers=driver_headers,
        json={"status": "delivered", "proof_note": "Entregado a cliente; recibido conforme."},
    )
    assert delivered.status_code == 200
    assert delivered.json()["status"] == "delivered"


def test_device_enrollment_token_is_required_for_print_claim(client, owner_headers) -> None:
    branch_id = client.get("/admin/branches", headers=owner_headers).json()[0]["id"]
    enrolled = client.post(
        "/admin/devices/enroll",
        headers=owner_headers,
        json={"branch_id": branch_id, "device_id": "POS-RTN-01", "name": "Caja principal"},
    )
    assert enrolled.status_code == 201
    token = enrolled.json()["token"]

    job = client.post(
        "/print-jobs",
        headers=owner_headers,
        json={"branch_id": branch_id, "device_id": "POS-RTN-01", "job_type": "receipt", "payload": "{\"text\":\"Mily Zebra\"}"},
    )
    assert job.status_code == 201

    unauthorized = client.post("/device/print-jobs/claim", headers={"X-Device-ID": "POS-RTN-01", "X-Device-Token": "wrong"})
    assert unauthorized.status_code == 401

    claimed = client.post(
        "/device/print-jobs/claim",
        headers={"X-Device-ID": "POS-RTN-01", "X-Device-Token": token},
    )
    assert claimed.status_code == 200
    assert claimed.json()["id"] == job.json()["id"]

    completed = client.post(
        f"/device/print-jobs/{job.json()['id']}/complete?success=true",
        headers={"X-Device-ID": "POS-RTN-01", "X-Device-Token": token},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
