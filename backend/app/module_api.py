from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import User, UserRole
from .module_registry import MODULES, TenantModule
from .security import get_current_user, require_roles
from .services import AuditService

module_router = APIRouter(prefix="/admin/modules", tags=["modules"])


def effective_enabled(db: Session, tenant_id: str, key: str) -> bool:
    definition = MODULES[key]
    row = db.scalar(
        select(TenantModule).where(
            TenantModule.tenant_id == tenant_id,
            TenantModule.module_key == key,
        )
    )
    if row is None:
        return definition.core
    return row.enabled


def require_enabled_module(module_key: str) -> Callable:
    if module_key not in MODULES:
        raise ValueError(f"Módulo no registrado: {module_key}")

    def dependency(
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> None:
        if not effective_enabled(db, user.tenant_id, module_key):
            raise HTTPException(status_code=403, detail=f"Módulo '{module_key}' desactivado")

    return dependency


def ensure_dependencies(db: Session, tenant_id: str, key: str) -> None:
    missing = [dep for dep in MODULES[key].dependencies if not effective_enabled(db, tenant_id, dep)]
    if missing:
        raise HTTPException(
            status_code=409,
            detail={"message": "Faltan dependencias del módulo", "missing": missing},
        )


@module_router.get("")
def list_modules(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.AUDITOR)),
) -> list[dict]:
    return [
        {
            "key": item.key,
            "name": item.name,
            "category": item.category,
            "dependencies": list(item.dependencies),
            "core": item.core,
            "enabled": effective_enabled(db, user.tenant_id, item.key),
        }
        for item in MODULES.values()
    ]


@module_router.put("/{module_key}")
def set_module(
    module_key: str,
    enabled: bool,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    definition = MODULES.get(module_key)
    if definition is None:
        raise HTTPException(status_code=404, detail="Módulo no registrado")
    if definition.core and not enabled:
        raise HTTPException(status_code=409, detail="Los módulos núcleo no se pueden desactivar")
    if enabled:
        ensure_dependencies(db, user.tenant_id, module_key)
    else:
        dependants = [
            key for key, candidate in MODULES.items()
            if module_key in candidate.dependencies and effective_enabled(db, user.tenant_id, key)
        ]
        if dependants:
            raise HTTPException(
                status_code=409,
                detail={"message": "Otros módulos dependen de este módulo", "dependants": dependants},
            )

    row = db.scalar(
        select(TenantModule).where(
            TenantModule.tenant_id == user.tenant_id,
            TenantModule.module_key == module_key,
        )
    )
    if row is None:
        row = TenantModule(tenant_id=user.tenant_id, module_key=module_key, enabled=enabled)
        db.add(row)
    else:
        row.enabled = enabled
    AuditService.record(
        db,
        user,
        "module.changed",
        "tenant_module",
        module_key,
        {"enabled": enabled},
    )
    db.commit()
    return {"key": module_key, "enabled": enabled}
