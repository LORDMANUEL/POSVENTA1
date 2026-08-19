from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image


def _product(client, headers, sku="PHOTO-001") -> str:
    response = client.post(
        "/products",
        headers=headers,
        json={
            "sku": sku,
            "name": "Vestido con fotos",
            "category": "Pink Vibes",
            "unit_cost": "250.00",
            "sale_price": "599.00",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _image(size=(900, 1200)) -> bytes:
    raw = BytesIO()
    Image.new("RGB", size, (240, 220, 230)).save(raw, format="JPEG", quality=90)
    return raw.getvalue()


def _zip(manifest: str, files: dict[str, bytes]) -> bytes:
    raw = BytesIO()
    with ZipFile(raw, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.csv", manifest)
        for name, payload in files.items():
            archive.writestr(name, payload)
    return raw.getvalue()


def test_media_zip_preview_commit_and_storefront_primary(client, owner_headers) -> None:
    product_id = _product(client, owner_headers)
    manifest = "sku,filename,position,primary\nPHOTO-001,photos/front.jpg,1,true\nPHOTO-001,photos/back.jpg,2,false\n"
    payload = _zip(manifest, {"photos/front.jpg": _image(), "photos/back.jpg": _image((1000, 1000))})

    preview = client.post(
        "/catalog/media-import/preview",
        headers=owner_headers,
        files={"file": ("photos.zip", payload, "application/zip")},
    )
    assert preview.status_code == 200
    assert preview.json()["valid"] is True
    assert preview.json()["image_count"] == 2
    assert preview.json()["preview"][0]["analysis"]["ready"] is True

    committed = client.post(
        "/catalog/media-import/commit",
        headers=owner_headers,
        files={"file": ("photos.zip", payload, "application/zip")},
    )
    assert committed.status_code == 201
    assert committed.json()["created"] == 2

    media = client.get(f"/media-admin/products/{product_id}", headers=owner_headers)
    assert media.status_code == 200
    assert len(media.json()) == 2
    primary = next(row for row in media.json() if row["primary"])
    assert primary["url"].endswith(".webp")
    assert primary["width"] == 900
    assert primary["height"] == 1200

    storefront = client.get("/store/mily-zebra/catalog")
    assert storefront.status_code == 200
    row = next(item for item in storefront.json()["products"] if item["id"] == product_id)
    assert row["primary_image_url"] == primary["url"]


def test_media_zip_rejects_unknown_sku_and_does_not_partially_import(client, owner_headers) -> None:
    product_id = _product(client, owner_headers)
    manifest = "sku,filename,position,primary\nPHOTO-001,ok.jpg,1,true\nNO-EXISTE,bad.jpg,1,true\n"
    payload = _zip(manifest, {"ok.jpg": _image(), "bad.jpg": _image()})

    committed = client.post(
        "/catalog/media-import/commit",
        headers=owner_headers,
        files={"file": ("photos.zip", payload, "application/zip")},
    )
    assert committed.status_code == 422
    media = client.get(f"/media-admin/products/{product_id}", headers=owner_headers)
    assert media.status_code == 200
    assert media.json() == []


def test_media_zip_rejects_path_traversal(client, owner_headers) -> None:
    _product(client, owner_headers)
    raw = BytesIO()
    with ZipFile(raw, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.csv", "sku,filename,position,primary\nPHOTO-001,../evil.jpg,1,true\n")
        archive.writestr("../evil.jpg", _image())

    response = client.post(
        "/catalog/media-import/preview",
        headers=owner_headers,
        files={"file": ("photos.zip", raw.getvalue(), "application/zip")},
    )
    assert response.status_code == 422
    assert "Ruta insegura" in str(response.json())
