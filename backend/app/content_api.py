import json
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .content_models import AdPlacement, Campaign, CmsPage
from .db import get_db
from .models import User, UserRole
from .module_api import require_enabled_module
from .security import require_roles
from .services import AuditService

cms_router = APIRouter(prefix="/cms", tags=["cms"], dependencies=[Depends(require_enabled_module("cms"))])
marketing_router = APIRouter(prefix="/marketing", tags=["marketing"], dependencies=[Depends(require_enabled_module("marketing"))])
ads_router = APIRouter(prefix="/ads", tags=["mily_ads"], dependencies=[Depends(require_enabled_module("mily_ads"))])


class CmsPageIn(BaseModel):
    slug: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=2, max_length=200)
    body: dict = Field(default_factory=dict)
    seo_title: str | None = Field(default=None, max_length=200)
    seo_description: str | None = Field(default=None, max_length=320)


class CampaignIn(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    channel: str = Field(pattern="^(email|whatsapp|social|web|ads)$")
    audience: dict = Field(default_factory=dict)
    content: dict = Field(default_factory=dict)
    budget: Decimal = Field(default=Decimal("0"), ge=0)
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class CampaignStatusIn(BaseModel):
    status: str = Field(pattern="^(draft|approved|scheduled|running|paused|completed|cancelled)$")


class AdPlacementIn(BaseModel):
    placement_key: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=2, max_length=160)
    content: dict = Field(default_factory=dict)


class AdMetricIn(BaseModel):
    metric: str = Field(pattern="^(impression|click|conversion)$")


@cms_router.get("/pages")
def list_pages(db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.AUDITOR))) -> list[dict]:
    rows = db.scalars(select(CmsPage).where(CmsPage.tenant_id == user.tenant_id).order_by(CmsPage.slug)).all()
    return [{"id": row.id, "slug": row.slug, "title": row.title, "status": row.status, "published_at": row.published_at} for row in rows]


@cms_router.post("/pages", status_code=201)
def create_page(payload: CmsPageIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER))) -> dict:
    if db.scalar(select(CmsPage.id).where(CmsPage.tenant_id == user.tenant_id, CmsPage.slug == payload.slug)):
        raise HTTPException(status_code=409, detail="Slug ya registrado")
    row = CmsPage(tenant_id=user.tenant_id, slug=payload.slug, title=payload.title, body_json=json.dumps(payload.body, ensure_ascii=False), seo_title=payload.seo_title, seo_description=payload.seo_description)
    db.add(row)
    db.flush()
    AuditService.record(db, user, "cms.page.created", "cms_page", row.id, {"slug": row.slug})
    db.commit()
    return {"id": row.id, "slug": row.slug, "status": row.status}


@cms_router.post("/pages/{page_id}/publish")
def publish_page(page_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER))) -> dict:
    row = db.scalar(select(CmsPage).where(CmsPage.id == page_id, CmsPage.tenant_id == user.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Página no encontrada")
    row.status = "published"
    row.published_at = datetime.now(timezone.utc)
    AuditService.record(db, user, "cms.page.published", "cms_page", row.id)
    db.commit()
    return {"id": row.id, "status": row.status, "published_at": row.published_at}


@marketing_router.get("/campaigns")
def list_campaigns(db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.SALES, UserRole.AUDITOR))) -> list[dict]:
    rows = db.scalars(select(Campaign).where(Campaign.tenant_id == user.tenant_id).order_by(Campaign.created_at.desc())).all()
    return [{"id": row.id, "name": row.name, "channel": row.channel, "status": row.status, "budget": str(row.budget), "starts_at": row.starts_at, "ends_at": row.ends_at} for row in rows]


@marketing_router.post("/campaigns", status_code=201)
def create_campaign(payload: CampaignIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER))) -> dict:
    if payload.starts_at and payload.ends_at and payload.ends_at <= payload.starts_at:
        raise HTTPException(status_code=422, detail="La fecha final debe ser posterior a la inicial")
    row = Campaign(tenant_id=user.tenant_id, name=payload.name, channel=payload.channel, audience_json=json.dumps(payload.audience, ensure_ascii=False), content_json=json.dumps(payload.content, ensure_ascii=False), budget=payload.budget, starts_at=payload.starts_at, ends_at=payload.ends_at)
    db.add(row)
    db.flush()
    AuditService.record(db, user, "campaign.created", "campaign", row.id, {"channel": row.channel, "budget": str(row.budget)})
    db.commit()
    return {"id": row.id, "status": row.status}


@marketing_router.put("/campaigns/{campaign_id}/status")
def change_campaign_status(campaign_id: str, payload: CampaignStatusIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER))) -> dict:
    row = db.scalar(select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == user.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    row.status = payload.status
    AuditService.record(db, user, "campaign.status", "campaign", row.id, {"status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status}


@ads_router.post("/placements", status_code=201)
def create_placement(payload: AdPlacementIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER))) -> dict:
    if db.scalar(select(AdPlacement.id).where(AdPlacement.tenant_id == user.tenant_id, AdPlacement.placement_key == payload.placement_key)):
        raise HTTPException(status_code=409, detail="Placement ya registrado")
    row = AdPlacement(tenant_id=user.tenant_id, placement_key=payload.placement_key, name=payload.name, content_json=json.dumps(payload.content, ensure_ascii=False))
    db.add(row)
    db.commit()
    return {"id": row.id, "placement_key": row.placement_key, "active": row.active}


@ads_router.post("/placements/{placement_id}/metric")
def record_metric(placement_id: str, payload: AdMetricIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.SALES, UserRole.SUPPORT))) -> dict:
    row = db.scalar(select(AdPlacement).where(AdPlacement.id == placement_id, AdPlacement.tenant_id == user.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Placement no encontrado")
    if payload.metric == "impression":
        row.impressions += 1
    elif payload.metric == "click":
        row.clicks += 1
    else:
        row.conversions += 1
    db.commit()
    return {"id": row.id, "impressions": row.impressions, "clicks": row.clicks, "conversions": row.conversions}
