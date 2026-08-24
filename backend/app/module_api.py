from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User, UserRole
from .module_registry import MODULES, TenantModule
from .security import get_current_user, require_roles
from .services import AuditService

module_router = APIRouter(prefix="/admin/modules", tags=["modules"])

# Modules whose complete internal runtime can be enabled without pretending that an
# external provider, physical device or fiscal homologation was certified.
FULL_INTERNAL_PROFILE = (
    "purchasing",
    "delivery",
    "returns",
    "crm",
    "loyalty",
    "notifications",
    "cms",
    "marketing",
    "mily_ads",
    "accounting",
    "receivables",
    "payables",
    "banking",
    "hr",
    "attendance",
    "payroll",
    "workflows",
    "integrations",
    "rag",
    "ai",
    "analytics",
)
EXTERNAL_GATED = {
    "payments": "Requiere proveedor/adquirente y sandbox certificado",
    "fiscal": "Requiere datos fiscales reales y homologación aplicable",
    "music": "Requiere reproductor/audio físico y validación de zona",
    "visual": "Requiere cámara/kiosco y adaptador visual certificado",
}
DEFAULT_ENABLED = frozenset(FULL_INTERNAL_PROFILE)


def external_mode(key: str) -> str:
    """Return deployment mode for an external-gated module.

    `sandbox` is software-certification mode only; it is never equivalent to a
    provider/physical certification. Production deployments should use
    `certified` only after external evidence has been completed and documented.
    """

    if key not in EXTERNAL_GATED:
        return "internal"
    settings = get_settings()
    if key in settings.certified_external_module_set:
        return "certified"
    if key in settings.sandbox_external_module_set:
        return "sandbox"
    return "blocked"


def external_ready(key: str) -> bool:
    return external_mode(key) != "blocked"


def effective_enabled(db: Session, tenant_id: str, key: str) -> bool:
    definition = MODULES[key]
    if not external_ready(key):
        # Fail closed even if a stale/legacy tenant_modules row says enabled.
        return False
    row = db.scalar(
        select(TenantModule).where(
            TenantModule.tenant_id == tenant_id,
            TenantModule.module_key == key,
        )
    )
    if row is None:
        # A freshly installed store is operational immediately: all software-only
        # modules that passed the stable gate are enabled by default. External-gated
        # modules remain opt-in even in sandbox/certified deployments.
        return definition.core or key in DEFAULT_ENABLED
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


def _set_enabled(db: Session, tenant_id: str, key: str, enabled: bool) -> None:
    row = db.scalar(
        select(TenantModule).where(
            TenantModule.tenant_id == tenant_id,
            TenantModule.module_key == key,
        )
    )
    if row is None:
        db.add(TenantModule(tenant_id=tenant_id, module_key=key, enabled=enabled))
    else:
        row.enabled = enabled


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
            "external_gate": EXTERNAL_GATED.get(item.key),
            "external_mode": external_mode(item.key) if item.key in EXTERNAL_GATED else None,
        }
        for item in MODULES.values()
    ]


@module_router.post("/profiles/full-internal/enable")
def enable_full_internal_profile(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    enabled: list[str] = []
    remaining = set(FULL_INTERNAL_PROFILE)
    while remaining:
        progressed = False
        for key in list(remaining):
            dependencies = MODULES[key].dependencies
            if all(effective_enabled(db, user.tenant_id, dep) or dep in enabled for dep in dependencies):
                _set_enabled(db, user.tenant_id, key, True)
                db.flush()
                enabled.append(key)
                remaining.remove(key)
                progressed = True
        if not progressed:
            raise HTTPException(
                status_code=409,
                detail={"message": "No se pudo resolver el grafo de módulos", "remaining": sorted(remaining)},
            )
    AuditService.record(
        db,
        user,
        "module.profile.enabled",
        "tenant_module_profile",
        "full-internal",
        {"enabled": enabled, "external_gated": sorted(EXTERNAL_GATED)},
    )
    db.commit()
    return {
        "profile": "full-internal",
        "enabled": enabled,
        "external_gated": EXTERNAL_GATED,
    }


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
    if enabled and module_key in EXTERNAL_GATED and not external_ready(module_key):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Módulo '{module_key}' bloqueado hasta completar certificación: "
                f"{EXTERNAL_GATED[module_key]}"
            ),
        )
    if enabled:
        ensure_dependencies(db, user.tenant_id, module_key)
    else:
        dependants = [
            key
            for key, candidate in MODULES.items()
            if module_key in candidate.dependencies and effective_enabled(db, user.tenant_id, key)
        ]
        if dependants:
            raise HTTPException(
                status_code=409,
                detail={"message": "Otros módulos dependen de este módulo", "dependants": dependants},
            )

    _set_enabled(db, user.tenant_id, module_key, enabled)
    AuditService.record(
        db,
        user,
        "module.changed",
        "tenant_module",
        module_key,
        {"enabled": enabled, "external_mode": external_mode(module_key)},
    )
    db.commit()
    return {"key": module_key, "enabled": enabled, "external_mode": external_mode(module_key)}
