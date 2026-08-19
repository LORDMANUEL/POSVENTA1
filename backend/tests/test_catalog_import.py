from io import BytesIO


def csv_file(text: str):
    return {"file": ("catalog.csv", BytesIO(text.encode("utf-8")), "text/csv")}


def test_catalog_import_preview_and_commit(client, owner_headers):
    content = (
        "sku,name,sale_price,unit_cost,barcode,description,category,size,color\n"
        "MZ-CSV-001,Blusa CSV,499.00,210.00,740000000001,Blusa fresca,Mily Basics,M,Rosa\n"
        "MZ-CSV-002,Bolso CSV,649.00,280.00,740000000002,Bolso pequeño,Mily Details,,Negro\n"
    )

    preview = client.post("/catalog/import/preview", headers=owner_headers, files=csv_file(content))
    assert preview.status_code == 200, preview.text
    assert preview.json()["valid"] is True
    assert preview.json()["row_count"] == 2

    commit = client.post("/catalog/import/commit", headers=owner_headers, files=csv_file(content))
    assert commit.status_code == 201, commit.text
    assert commit.json()["created"] == 2

    duplicate_preview = client.post("/catalog/import/preview", headers=owner_headers, files=csv_file(content))
    assert duplicate_preview.status_code == 200
    assert duplicate_preview.json()["valid"] is False

    duplicate_commit = client.post("/catalog/import/commit", headers=owner_headers, files=csv_file(content))
    assert duplicate_commit.status_code == 409


def test_catalog_import_rejects_duplicate_sku_inside_file(client, owner_headers):
    content = (
        "sku,name,sale_price\n"
        "MZ-DUP-001,Producto Uno,100.00\n"
        "MZ-DUP-001,Producto Dos,120.00\n"
    )
    preview = client.post("/catalog/import/preview", headers=owner_headers, files=csv_file(content))
    assert preview.status_code == 200
    assert preview.json()["valid"] is False

    commit = client.post("/catalog/import/commit", headers=owner_headers, files=csv_file(content))
    assert commit.status_code == 422
