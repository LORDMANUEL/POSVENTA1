from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import get_db
from .models import Branch, Tenant, User, UserRole
from .platform_access import ensure_platform_operator, is_platform_admin, require_platform_admin
from .security import get_current_user, hash_password
from .services import AuditService

platform_router = APIRouter(prefix="/platform", tags=["platform"])


class TenantProvisionIn(BaseModel):
    store_name: str = Field(min_length=2, max_length=160)
    store_slug: str = Field(
        min_length=2,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    branch_name: str = Field(min_length=2, max_length=120)
    branch_code: str = Field(min_length=2, max_length=30)
    owner_email: str = Field(min_length=5, max_length=255)
    owner_full_name: str = Field(min_length=2, max_length=160)
    owner_password: str = Field(min_length=10, max_length=128)


def _tenant_paths(slug: str) -> dict[str, str]:
    return {
        "admin_login_path": f"/admin?tenant={slug}",
        "storefront_path": f"/?store={slug}",
    }


@platform_router.get("/access")
def platform_access(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return {"platform_admin": is_platform_admin(db, user)}


@platform_router.get("/tenants")
def list_tenants(
    db: Session = Depends(get_db),
    _: User = Depends(require_platform_admin),
) -> list[dict]:
    rows = db.execute(
        select(
            Tenant.id,
            Tenant.name,
            Tenant.slug,
            Tenant.active,
            Tenant.created_at,
            func.count(Branch.id),
        )
        .outerjoin(Branch, Branch.tenant_id == Tenant.id)
        .group_by(Tenant.id, Tenant.name, Tenant.slug, Tenant.active, Tenant.created_at)
        .order_by(Tenant.created_at, Tenant.slug)
    ).all()
    return [
        {
            "id": row[0],
            "name": row[1],
            "slug": row[2],
            "active": row[3],
            "created_at": row[4],
            "branch_count": int(row[5] or 0),
            **_tenant_paths(row[2]),
        }
        for row in rows
    ]


@platform_router.post("/tenants", status_code=201)
def create_tenant(
    payload: TenantProvisionIn,
    db: Session = Depends(get_db),
    platform_user: User = Depends(require_platform_admin),
) -> dict:
    slug = payload.store_slug.lower().strip()
    email = payload.owner_email.lower().strip()
    branch_code = payload.branch_code.upper().strip()

    if db.scalar(select(Tenant.id).where(Tenant.slug == slug)):
        raise HTTPException(status_code=409, detail="Slug de tienda ya registrado")

    try:
        ensure_platform_operator(db, platform_user)
        tenant = Tenant(name=payload.store_name.strip(), slug=slug)
        db.add(tenant)
        db.flush()
        branch = Branch(
            tenant_id=tenant.id,
            code=branch_code,
            name=payload.branch_name.strip(),
        )
        db.add(branch)
        db.flush()
        owner = User(
            tenant_id=tenant.id,
            branch_id=branch.id,
            email=email,
            full_name=payload.owner_full_name.strip(),
            password_hash=hash_password(payload.owner_password),
            role=UserRole.OWNER,
        )
        db.add(owner)
        db.flush()
        AuditService.record(
            db,
            platform_user,
            "platform.tenant_created",
            "tenant",
            tenant.id,
            {"slug": slug, "owner_user_id": owner.id, "branch_id": branch.id},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="La empresa, sucursal o propietario entró en conflicto con datos existentes",
        ) from exc

    return {
        "tenant": {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "active": tenant.active,
        },
        "branch": {
            "id": branch.id,
            "code": branch.code,
            "name": branch.name,
        },
        "owner": {
            "id": owner.id,
            "email": owner.email,
            "full_name": owner.full_name,
            "role": owner.role.value,
            "platform_admin": False,
        },
        **_tenant_paths(tenant.slug),
    }
