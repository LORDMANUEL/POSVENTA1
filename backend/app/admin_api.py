import hashlib
import secrets
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .admin_models import Device
from .db import get_db
from .models import Branch, PrintJob, PrintJobStatus, User, UserRole
from .security import require_roles
from .services import AuditService

admin_router = APIRouter(prefix="/admin", tags=["admin"])
device_router = APIRouter(prefix="/device", tags=["device"])


class BranchIn(BaseModel):
    code: str = Field(min_length=2, max_length=30)
    name: str = Field(min_length=2, max_length=120)


class DeviceEnrollIn(BaseModel):
    branch_id: str
    device_id: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=2, max_length=160)
    kind: str = Field(default="hardware-agent", max_length=40)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_current_device(
    x_device_id: Annotated[str, Header(alias="X-Device-ID")],
    x_device_token: Annotated[str, Header(alias="X-Device-Token")],
    db: Session = Depends(get_db),
) -> Device:
    supplied_hash = token_hash(x_device_token)
    device = db.scalar(
        select(Device).where(
            Device.device_id == x_device_id,
            Device.token_hash == supplied_hash,
            Device.active.is_(True),
        )
    )
    if not device or not secrets.compare_digest(device.token_hash, supplied_hash):
        raise HTTPException(status_code=401, detail="Dispositivo no autorizado")
    device.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return device


@admin_router.get("/branches")
def list_branches(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.AUDITOR)),
) -> list[dict]:
    branches = db.scalars(select(Branch).where(Branch.tenant_id == user.tenant_id).order_by(Branch.code)).all()
    return [{"id": b.id, "code": b.code, "name": b.name, "active": b.active} for b in branches]


@admin_router.post("/branches", status_code=201)
def create_branch(
    payload: BranchIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    if db.scalar(select(Branch.id).where(Branch.tenant_id == user.tenant_id, Branch.code == payload.code)):
        raise HTTPException(status_code=409, detail="Código de sucursal ya registrado")
    branch = Branch(tenant_id=user.tenant_id, code=payload.code, name=payload.name)
    db.add(branch)
    db.flush()
    AuditService.record(db, user, "branch.created", "branch", branch.id, {"code": branch.code})
    db.commit()
    return {"id": branch.id, "code": branch.code, "name": branch.name}


@admin_router.get("/devices")
def list_devices(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.SUPPORT)),
) -> list[dict]:
    devices = db.scalars(select(Device).where(Device.tenant_id == user.tenant_id).order_by(Device.name)).all()
    return [
        {
            "id": d.id,
            "device_id": d.device_id,
            "branch_id": d.branch_id,
            "name": d.name,
            "kind": d.kind,
            "active": d.active,
            "last_seen_at": d.last_seen_at,
        }
        for d in devices
    ]


@admin_router.post("/devices/enroll", status_code=201)
def enroll_device(
    payload: DeviceEnrollIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    branch = db.scalar(select(Branch).where(Branch.id == payload.branch_id, Branch.tenant_id == user.tenant_id))
    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    if db.scalar(select(Device.id).where(Device.tenant_id == user.tenant_id, Device.device_id == payload.device_id)):
        raise HTTPException(status_code=409, detail="Device ID ya registrado")
    plain_token = secrets.token_urlsafe(32)
    device = Device(
        tenant_id=user.tenant_id,
        branch_id=branch.id,
        device_id=payload.device_id,
        name=payload.name,
        kind=payload.kind,
        token_hash=token_hash(plain_token),
    )
    db.add(device)
    db.flush()
    AuditService.record(db, user, "device.enrolled", "device", device.id, {"device_id": device.device_id})
    db.commit()
    return {
        "id": device.id,
        "device_id": device.device_id,
        "branch_id": device.branch_id,
        "token": plain_token,
        "warning": "Este token se muestra una sola vez; guárdelo en la configuración local del agente.",
    }


@device_router.post("/print-jobs/claim")
def device_claim_print_job(
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> dict | None:
    job = db.scalar(
        select(PrintJob)
        .where(
            PrintJob.tenant_id == device.tenant_id,
            PrintJob.branch_id == device.branch_id,
            PrintJob.status == PrintJobStatus.QUEUED,
            (PrintJob.device_id.is_(None) | (PrintJob.device_id == device.device_id)),
        )
        .order_by(PrintJob.created_at)
        .limit(1)
    )
    if not job:
        return None
    job.status = PrintJobStatus.CLAIMED
    job.device_id = device.device_id
    job.claimed_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": job.id, "job_type": job.job_type, "payload": job.payload}


@device_router.post("/print-jobs/{job_id}/complete")
def device_complete_print_job(
    job_id: str,
    success: bool,
    error: str | None = None,
    db: Session = Depends(get_db),
    device: Device = Depends(get_current_device),
) -> dict:
    job = db.scalar(
        select(PrintJob).where(
            PrintJob.id == job_id,
            PrintJob.tenant_id == device.tenant_id,
            PrintJob.branch_id == device.branch_id,
            PrintJob.device_id == device.device_id,
            PrintJob.status == PrintJobStatus.CLAIMED,
        )
    )
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo reclamado no encontrado")
    job.status = PrintJobStatus.COMPLETED if success else PrintJobStatus.FAILED
    job.error = error
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": job.id, "status": job.status.value}
