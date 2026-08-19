import csv
from decimal import Decimal, InvalidOperation
from io import StringIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Product, User, UserRole
from .module_api import require_enabled_module
from .security import require_roles
from .services import AuditService

catalog_import_router = APIRouter(
    prefix="/catalog/import",
    tags=["catalog-import"],
    dependencies=[Depends(require_enabled_module("catalog"))],
)
MAX_IMPORT_BYTES = 2 * 1024 * 1024
REQUIRED_HEADERS = {"sku", "name", "sale_price"}


class CatalogRow(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=180)
    sale_price: Decimal = Field(ge=0)
    unit_cost: Decimal = Field(default=Decimal("0"), ge=0)
    barcode: str | None = Field(default=None, max_length=80)
    description: str = Field(default="", max_length=5000)
    category: str = Field(default="general", max_length=80)
    size: str | None = Field(default=None, max_length=30)
    color: str | None = Field(default=None, max_length=60)


class ParsedImport(BaseModel):
    rows: list[CatalogRow]
    errors: list[dict]


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _parse(raw: bytes) -> ParsedImport:
    if not raw:
        raise HTTPException(status_code=422, detail="Archivo CSV vacío")
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="El CSV excede el límite de 2 MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="El CSV debe estar codificado en UTF-8") from exc

    reader = csv.DictReader(StringIO(text))
    headers = {header.strip() for header in (reader.fieldnames or []) if header}
    missing = sorted(REQUIRED_HEADERS - headers)
    if missing:
        raise HTTPException(status_code=422, detail={"message": "Faltan columnas obligatorias", "missing": missing})

    rows: list[CatalogRow] = []
    errors: list[dict] = []
    seen_skus: set[str] = set()
    for row_number, source in enumerate(reader, start=2):
        try:
            sku = (source.get("sku") or "").strip()
            if sku in seen_skus:
                raise ValueError("SKU repetido dentro del archivo")
            try:
                sale_price = Decimal((source.get("sale_price") or "").strip())
                unit_cost = Decimal((source.get("unit_cost") or "0").strip() or "0")
            except InvalidOperation as exc:
                raise ValueError("Costo o precio no es un número decimal válido") from exc
            parsed = CatalogRow(
                sku=sku,
                name=(source.get("name") or "").strip(),
                sale_price=sale_price,
                unit_cost=unit_cost,
                barcode=_normalize_optional(source.get("barcode")),
                description=(source.get("description") or "").strip(),
                category=(source.get("category") or "general").strip() or "general",
                size=_normalize_optional(source.get("size")),
                color=_normalize_optional(source.get("color")),
            )
            seen_skus.add(parsed.sku)
            rows.append(parsed)
        except (ValidationError, ValueError) as exc:
            errors.append({"row": row_number, "error": str(exc)})
    return ParsedImport(rows=rows, errors=errors)


def _read_upload(file: UploadFile) -> bytes:
    return file.file.read(MAX_IMPORT_BYTES + 1)


@catalog_import_router.post("/preview")
def preview_catalog_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE)),
) -> dict:
    parsed = _parse(_read_upload(file))
    existing_skus = set(
        db.scalars(
            select(Product.sku).where(
                Product.tenant_id == user.tenant_id,
                Product.sku.in_([row.sku for row in parsed.rows] or ["__none__"]),
            )
        ).all()
    )
    errors = list(parsed.errors)
    for index, row in enumerate(parsed.rows, start=2):
        if row.sku in existing_skus:
            errors.append({"row": index, "sku": row.sku, "error": "SKU ya existe en la tienda"})
    return {
        "valid": not errors,
        "row_count": len(parsed.rows),
        "errors": errors,
        "preview": [row.model_dump(mode="json") for row in parsed.rows[:50]],
    }


@catalog_import_router.post("/commit", status_code=201)
def commit_catalog_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict:
    parsed = _parse(_read_upload(file))
    if parsed.errors:
        raise HTTPException(status_code=422, detail={"message": "El archivo contiene errores", "errors": parsed.errors})
    skus = [row.sku for row in parsed.rows]
    existing_skus = set(
        db.scalars(
            select(Product.sku).where(Product.tenant_id == user.tenant_id, Product.sku.in_(skus or ["__none__"]))
        ).all()
    )
    if existing_skus:
        raise HTTPException(
            status_code=409,
            detail={"message": "Hay SKU ya existentes; no se importó ninguna fila", "skus": sorted(existing_skus)},
        )
    if not parsed.rows:
        raise HTTPException(status_code=422, detail="El CSV no contiene productos")

    created: list[str] = []
    for row in parsed.rows:
        product = Product(
            tenant_id=user.tenant_id,
            sku=row.sku,
            barcode=row.barcode,
            name=row.name,
            description=row.description,
            category=row.category,
            size=row.size,
            color=row.color,
            unit_cost=row.unit_cost,
            sale_price=row.sale_price,
        )
        db.add(product)
        db.flush()
        created.append(product.id)
    AuditService.record(
        db,
        user,
        "catalog.bulk_imported",
        "product",
        None,
        {"count": len(created), "skus": skus[:100]},
    )
    db.commit()
    return {"created": len(created), "product_ids": created}
