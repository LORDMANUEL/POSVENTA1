import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .experience_models import Announcement, AudioZone, KioskHeartbeat, Playlist, VisualSession
from .models import Branch, User, UserRole
from .module_api import require_enabled_module
from .security import require_roles
from .services import AuditService

music_router = APIRouter(prefix="/music", tags=["music"], dependencies=[Depends(require_enabled_module("music"))])
visual_router = APIRouter(prefix="/visual", tags=["visual"], dependencies=[Depends(require_enabled_module("visual"))])


class ZoneIn(BaseModel):
    branch_id: str
    name: str = Field(min_length=2, max_length=120)
    player_device_id: str | None = Field(default=None, max_length=120)


class PlaylistIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    items: list[dict] = Field(default_factory=list)


class AnnouncementIn(BaseModel):
    zone_id: str
    text: str = Field(min_length=1, max_length=2000)
    audio_url: str | None = None
    duck_music: bool = True
    scheduled_at: datetime | None = None


class VisualSessionIn(BaseModel):
    customer_id: str | None = None
    branch_id: str | None = None
    session_type: str = Field(default="virtual_fitting", max_length=40)
    consent_granted: bool
    input_locator: str | None = None
    ttl_minutes: int = Field(default=30, ge=5, le=1440)


class VisualCompleteIn(BaseModel):
    result_locator: str = Field(min_length=1, max_length=2000)


class KioskHeartbeatIn(BaseModel):
    branch_id: str
    device_id: str = Field(min_length=2, max_length=120)
    status: str = Field(default="online", max_length=24)


@music_router.post("/zones", status_code=201)
def create_zone(payload: ZoneIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER))) -> dict:
    if not db.scalar(select(Branch.id).where(Branch.id == payload.branch_id, Branch.tenant_id == user.tenant_id)):
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    row = AudioZone(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(row)
    db.flush()
    AuditService.record(db, user, "audio.zone.created", "audio_zone", row.id, {"name": row.name})
    db.commit()
    return {"id": row.id, "name": row.name, "active": row.active}


@music_router.post("/playlists", status_code=201)
def create_playlist(payload: PlaylistIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER))) -> dict:
    row = Playlist(tenant_id=user.tenant_id, name=payload.name, items_json=json.dumps(payload.items, ensure_ascii=False))
    db.add(row)
    db.commit()
    return {"id": row.id, "name": row.name, "active": row.active}


@music_router.post("/announcements", status_code=201)
def queue_announcement(payload: AnnouncementIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.SUPPORT))) -> dict:
    zone = db.scalar(select(AudioZone).where(AudioZone.id == payload.zone_id, AudioZone.tenant_id == user.tenant_id, AudioZone.active.is_(True)))
    if not zone:
        raise HTTPException(status_code=404, detail="Zona de audio activa no encontrada")
    row = Announcement(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(row)
    db.flush()
    AuditService.record(db, user, "announcement.queued", "announcement", row.id, {"zone_id": zone.id})
    db.commit()
    return {"id": row.id, "status": row.status, "duck_music": row.duck_music}


@visual_router.post("/sessions", status_code=201)
def create_visual_session(payload: VisualSessionIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.SALES, UserRole.SUPPORT))) -> dict:
    if not payload.consent_granted:
        raise HTTPException(status_code=422, detail="El consentimiento explícito es obligatorio para una sesión visual")
    row = VisualSession(
        tenant_id=user.tenant_id,
        customer_id=payload.customer_id,
        branch_id=payload.branch_id or user.branch_id,
        session_type=payload.session_type,
        consent_granted=True,
        input_locator=payload.input_locator,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=payload.ttl_minutes),
    )
    db.add(row)
    db.flush()
    AuditService.record(db, user, "visual.session.created", "visual_session", row.id, {"type": row.session_type, "expires_at": row.expires_at})
    db.commit()
    return {"id": row.id, "status": row.status, "expires_at": row.expires_at}


@visual_router.post("/sessions/{session_id}/complete")
def complete_visual_session(session_id: str, payload: VisualCompleteIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.SALES, UserRole.SUPPORT))) -> dict:
    row = db.scalar(select(VisualSession).where(VisualSession.id == session_id, VisualSession.tenant_id == user.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Sesión visual no encontrada")
    if row.expires_at < datetime.now(timezone.utc):
        row.status = "expired"
        db.commit()
        raise HTTPException(status_code=410, detail="Sesión visual expirada")
    row.result_locator = payload.result_locator
    row.status = "completed"
    db.commit()
    return {"id": row.id, "status": row.status, "result_locator": row.result_locator}


@visual_router.post("/kiosk/heartbeat")
def kiosk_heartbeat(payload: KioskHeartbeatIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.SUPPORT))) -> dict:
    row = db.scalar(select(KioskHeartbeat).where(KioskHeartbeat.tenant_id == user.tenant_id, KioskHeartbeat.device_id == payload.device_id))
    if row is None:
        row = KioskHeartbeat(tenant_id=user.tenant_id, branch_id=payload.branch_id, device_id=payload.device_id, status=payload.status)
        db.add(row)
    else:
        row.branch_id = payload.branch_id
        row.status = payload.status
        row.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return {"device_id": row.device_id, "status": row.status, "last_seen_at": row.last_seen_at}
