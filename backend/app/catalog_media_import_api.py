import csv
from io import BytesIO, StringIO
from pathlib import Path, PurePosixPath
import uuid
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .media_models import ProductMedia
from .models import Product, User, UserRole
from .module_api import require_enabled_module
from .security import require_roles
from .services import AuditService

router = APIRouter(
    prefix="/catalog/media-import",
    tags=["catalog-media-import"],
    dependencies=[Depends(require_enabled_module("catalog"))],
)
settings = get_settings()

MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_FILES = 500
MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MANIFEST_HEADERS = {"sku", "filename", "position", "primary"}


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def _read_zip(upload: UploadFile) -> bytes:
    raw = upload.file.read(MAX_ZIP_BYTES + 1)
    if not raw:
        raise HTTPException(status_code=422, detail="ZIP vacío")
    if len(raw) > MAX_ZIP_BYTES:
        raise HTTPException(status_code=413, detail="El ZIP excede 50 MB")
    return raw


def _open_safe_zip(raw: bytes) -> ZipFile:
    try:
        archive = ZipFile(BytesIO(raw))
    except BadZipFile as exc:
        raise HTTPException(status_code=422, detail="Archivo ZIP inválido") from exc
    infos = [item for item in archive.infolist() if not item.is_dir()]
    if len(infos) > MAX_FILES:
        archive.close()
        raise HTTPException(status_code=413, detail="El ZIP contiene demasiados archivos")
    total = 0
    for item in infos:
        if not _safe_member(item.filename):
            archive.close()
            raise HTTPException(status_code=422, detail=f"Ruta insegura en ZIP: {item.filename}")
        total += item.file_size
        if total > MAX_UNCOMPRESSED_BYTES:
            archive.close()
            raise HTTPException(status_code=413, detail="El ZIP excede el tamaño descomprimido permitido")
        compressed = max(item.compress_size, 1)
        if item.file_size / compressed > MAX_COMPRESSION_RATIO:
            archive.close()
            raise HTTPException(status_code=413, detail=f"Compresión sospechosa en {item.filename}")
    return archive


def _manifest(archive: ZipFile) -> list[dict]:
    names = {item.filename for item in archive.infolist()}
    manifest_name = next((name for name in names if name.lower() == "manifest.csv"), None)
    if not manifest_name:
        raise HTTPException(status_code=422, detail="El ZIP debe incluir manifest.csv en la raíz")
    try:
        text = archive.read(manifest_name).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="manifest.csv debe estar en UTF-8") from exc
    reader = csv.DictReader(StringIO(text))
    headers = {str(h).strip().lower() for h in (reader.fieldnames or []) if h}
    missing = sorted(MANIFEST_HEADERS - headers)
    if missing:
        raise HTTPException(status_code=422, detail={"message": "Faltan columnas en manifest.csv", "missing": missing})
    rows = []
    seen_files = set()
    for number, source in enumerate(reader, start=2):
        sku = (source.get("sku") or "").strip()
        filename = (source.get("filename") or "").strip().replace("\\", "/")
        try:
            position = int((source.get("position") or "0").strip())
        except ValueError:
            position = 0
        primary_text = (source.get("primary") or "false").strip().lower()
        primary = primary_text in {"1", "true", "yes", "si", "sí"}
        if not sku or not filename or position < 1:
            rows.append({"row": number, "sku": sku, "filename": filename, "error": "SKU, filename y position>=1 son obligatorios"})
            continue
        if filename in seen_files:
            rows.append({"row": number, "sku": sku, "filename": filename, "error": "Archivo repetido en manifest"})
            continue
        seen_files.add(filename)
        rows.append({"row": number, "sku": sku, "filename": filename, "position": position, "primary": primary})
    return rows


def _analyze_image(raw: bytes) -> tuple[dict, bytes]:
    if not raw:
        raise ValueError("imagen vacía")
    if len(raw) > settings.max_image_bytes:
        raise ValueError("imagen excede el límite individual")
    try:
        with Image.open(BytesIO(raw)) as source:
            source.verify()
        with Image.open(BytesIO(raw)) as source:
            if source.format not in ALLOWED_FORMATS:
                raise ValueError("formato no permitido; use JPEG, PNG o WebP")
            original_format = source.format
            image = ImageOps.exif_transpose(source)
            width, height = image.size
            issues = []
            if width < 600 or height < 600:
                issues.append("resolución_baja")
            ratio = max(width, height) / max(min(width, height), 1)
            if ratio > 3.5:
                issues.append("relacion_aspecto_extrema")
            if width > 5000 or height > 5000:
                issues.append("resolución_excesiva")
            has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if has_alpha else "RGB")
            image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
            out_width, out_height = image.size
            encoded = BytesIO()
            image.save(encoded, format="WEBP", quality=88, method=6)
            analysis = {
                "format": original_format,
                "width": width,
                "height": height,
                "normalized_width": out_width,
                "normalized_height": out_height,
                "orientation": "square" if width == height else ("portrait" if height > width else "landscape"),
                "megapixels": round((width * height) / 1_000_000, 2),
                "has_alpha": has_alpha,
                "issues": issues,
                "ready": not issues,
            }
            return analysis, encoded.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError(str(exc) or "imagen inválida") from exc


def _validate(archive: ZipFile, db: Session, tenant_id: str) -> dict:
    rows = _manifest(archive)
    names = {item.filename for item in archive.infolist() if not item.is_dir()}
    manifest_errors = [row for row in rows if "error" in row]
    valid_rows = [row for row in rows if "error" not in row]
    skus = sorted({row["sku"] for row in valid_rows})
    products = db.scalars(select(Product).where(Product.tenant_id == tenant_id, Product.sku.in_(skus or ["__none__"]))).all()
    by_sku = {product.sku: product for product in products}
    existing_counts = {
        product_id: count
        for product_id, count in db.execute(
            select(ProductMedia.product_id, func.count(ProductMedia.id))
            .where(ProductMedia.tenant_id == tenant_id)
            .group_by(ProductMedia.product_id)
        ).all()
    }
    errors = list(manifest_errors)
    preview = []
    per_product = {}
    primary_by_sku = {}
    for row in valid_rows:
        sku = row["sku"]
        product = by_sku.get(sku)
        if not product:
            errors.append({**row, "error": "SKU no existe en la tienda"})
            continue
        if row["filename"] not in names:
            errors.append({**row, "error": "Archivo no existe dentro del ZIP"})
            continue
        per_product[sku] = per_product.get(sku, 0) + 1
        if existing_counts.get(product.id, 0) + per_product[sku] > 5:
            errors.append({**row, "error": "El producto excedería el máximo de 5 imágenes"})
            continue
        if row["primary"]:
            primary_by_sku[sku] = primary_by_sku.get(sku, 0) + 1
            if primary_by_sku[sku] > 1:
                errors.append({**row, "error": "Solo puede existir una imagen primary por SKU en el manifest"})
                continue
        try:
            analysis, _ = _analyze_image(archive.read(row["filename"]))
        except (KeyError, ValueError) as exc:
            errors.append({**row, "error": str(exc)})
            continue
        preview.append({**row, "product_id": product.id, "analysis": analysis})
    return {"valid": not errors, "image_count": len(preview), "errors": errors, "preview": preview}


@router.post("/preview")
def preview_media_zip(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE)),
) -> dict:
    archive = _open_safe_zip(_read_zip(file))
    try:
        return _validate(archive, db, user.tenant_id)
    finally:
        archive.close()


@router.post("/commit", status_code=201)
def commit_media_zip(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict:
    archive = _open_safe_zip(_read_zip(file))
    written: list[Path] = []
    try:
        validation = _validate(archive, db, user.tenant_id)
        if not validation["valid"]:
            raise HTTPException(status_code=422, detail={"message": "El ZIP contiene errores; no se importó ninguna imagen", "errors": validation["errors"]})
        products = {p.sku: p for p in db.scalars(select(Product).where(Product.tenant_id == user.tenant_id)).all()}
        root = Path(settings.media_root)
        created = []
        for row in validation["preview"]:
            product = products[row["sku"]]
            _, encoded = _analyze_image(archive.read(row["filename"]))
            relative = Path(user.tenant_id) / product.id / f"{uuid.uuid4().hex}.webp"
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(encoded)
            written.append(destination)
            if row["primary"]:
                for existing in db.scalars(select(ProductMedia).where(ProductMedia.tenant_id == user.tenant_id, ProductMedia.product_id == product.id, ProductMedia.primary.is_(True))).all():
                    existing.primary = False
            media = ProductMedia(
                tenant_id=user.tenant_id,
                product_id=product.id,
                storage_path=str(relative),
                public_url=f"/media/{relative.as_posix()}",
                width=row["analysis"]["normalized_width"],
                height=row["analysis"]["normalized_height"],
                position=row["position"],
                primary=row["primary"],
            )
            db.add(media)
            db.flush()
            created.append(media.id)
        # If no primary was explicitly provided for a product without media, make its first imported image primary.
        product_ids = {products[row["sku"]].id for row in validation["preview"]}
        for product_id in product_ids:
            has_primary = db.scalar(select(ProductMedia.id).where(ProductMedia.tenant_id == user.tenant_id, ProductMedia.product_id == product_id, ProductMedia.primary.is_(True)).limit(1))
            if not has_primary:
                first = db.scalar(select(ProductMedia).where(ProductMedia.tenant_id == user.tenant_id, ProductMedia.product_id == product_id).order_by(ProductMedia.position, ProductMedia.id).limit(1))
                if first:
                    first.primary = True
        AuditService.record(db, user, "catalog.media_bulk_imported", "product_media", None, {"count": len(created)})
        db.commit()
        return {"created": len(created), "media_ids": created}
    except Exception:
        db.rollback()
        for path in written:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    finally:
        archive.close()
