from io import BytesIO
from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .media_models import ProductMedia
from .models import Product, User, UserRole
from .security import get_current_user, require_roles
from .services import AuditService

media_router = APIRouter(prefix="/media-admin", tags=["media"])
settings = get_settings()
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def _product(db: Session, tenant_id: str, product_id: str) -> Product:
    product = db.scalar(select(Product).where(Product.id == product_id, Product.tenant_id == tenant_id))
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return product


@media_router.get("/products/{product_id}")
def list_product_media(
    product_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    _product(db, user.tenant_id, product_id)
    rows = db.scalars(
        select(ProductMedia)
        .where(ProductMedia.tenant_id == user.tenant_id, ProductMedia.product_id == product_id)
        .order_by(ProductMedia.position)
    ).all()
    return [
        {
            "id": row.id,
            "url": row.public_url,
            "width": row.width,
            "height": row.height,
            "position": row.position,
            "primary": row.primary,
        }
        for row in rows
    ]


@media_router.post("/products/{product_id}", status_code=201)
def upload_product_media(
    product_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE)),
) -> dict:
    _product(db, user.tenant_id, product_id)
    count = db.scalar(
        select(func.count(ProductMedia.id)).where(
            ProductMedia.tenant_id == user.tenant_id,
            ProductMedia.product_id == product_id,
        )
    )
    if int(count or 0) >= 5:
        raise HTTPException(status_code=409, detail="Cada producto admite un máximo de 5 imágenes")

    raw = file.file.read(settings.max_image_bytes + 1)
    if len(raw) > settings.max_image_bytes:
        raise HTTPException(status_code=413, detail="La imagen excede el límite de 10 MB")
    if not raw:
        raise HTTPException(status_code=422, detail="Archivo de imagen vacío")

    try:
        with Image.open(BytesIO(raw)) as source:
            source.verify()
        with Image.open(BytesIO(raw)) as source:
            if source.format not in ALLOWED_FORMATS:
                raise HTTPException(status_code=415, detail="Formato no permitido; use JPEG, PNG o WebP")
            image = ImageOps.exif_transpose(source)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
            width, height = image.size
            output = BytesIO()
            image.save(output, format="WEBP", quality=88, method=6)
            encoded = output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="El archivo no es una imagen válida") from exc

    relative = Path(user.tenant_id) / product_id / f"{uuid.uuid4().hex}.webp"
    root = Path(settings.media_root)
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(encoded)

    max_position = db.scalar(
        select(func.coalesce(func.max(ProductMedia.position), 0)).where(ProductMedia.product_id == product_id)
    )
    position = int(max_position or 0) + 1
    media = ProductMedia(
        tenant_id=user.tenant_id,
        product_id=product_id,
        storage_path=str(relative),
        public_url=f"/media/{relative.as_posix()}",
        width=width,
        height=height,
        position=position,
        primary=position == 1,
    )
    db.add(media)
    db.flush()
    AuditService.record(db, user, "product.media_added", "product_media", media.id, {"product_id": product_id})
    db.commit()
    return {
        "id": media.id,
        "url": media.public_url,
        "width": media.width,
        "height": media.height,
        "position": media.position,
        "primary": media.primary,
    }


@media_router.delete("/{media_id}", status_code=204)
def delete_product_media(
    media_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE)),
) -> None:
    media = db.scalar(
        select(ProductMedia).where(ProductMedia.id == media_id, ProductMedia.tenant_id == user.tenant_id)
    )
    if not media:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    product_id = media.product_id
    path = Path(settings.media_root) / media.storage_path
    was_primary = media.primary
    db.delete(media)
    db.flush()
    if was_primary:
        replacement = db.scalar(
            select(ProductMedia)
            .where(ProductMedia.product_id == product_id, ProductMedia.tenant_id == user.tenant_id)
            .order_by(ProductMedia.position)
            .limit(1)
        )
        if replacement:
            replacement.primary = True
    AuditService.record(db, user, "product.media_deleted", "product_media", media_id, {"product_id": product_id})
    db.commit()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # DB state remains authoritative; orphan cleanup can remove inaccessible files later.
        pass
