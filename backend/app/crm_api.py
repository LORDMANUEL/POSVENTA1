import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .crm_models import Consent, Lead, LoyaltyEntry, Notification, Opportunity
from .db import get_db
from .models import User, UserRole
from .module_api import require_enabled_module
from .ops_models import Customer
from .security import require_roles
from .services import AuditService

crm_router = APIRouter(prefix="/crm", tags=["crm"], dependencies=[Depends(require_enabled_module("crm"))])
loyalty_router = APIRouter(prefix="/loyalty", tags=["loyalty"], dependencies=[Depends(require_enabled_module("loyalty"))])
notification_router = APIRouter(prefix="/notifications", tags=["notifications"], dependencies=[Depends(require_enabled_module("notifications"))])


class LeadIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=180)
    email: str | None = None
    phone: str | None = None
    source: str = Field(default="manual", max_length=60)
    notes: str = ""


class OpportunityIn(BaseModel):
    lead_id: str | None = None
    customer_id: str | None = None
    title: str = Field(min_length=2, max_length=180)
    expected_value: Decimal = Field(default=Decimal("0"), ge=0)
    probability: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    notes: str = ""


class OpportunityStageIn(BaseModel):
    stage: str = Field(pattern="^(qualification|proposal|negotiation|won|lost)$")


class LoyaltyIn(BaseModel):
    customer_id: str
    points_delta: Decimal
    reason: str = Field(min_length=2, max_length=120)
    reference_type: str | None = None
    reference_id: str | None = None


class ConsentIn(BaseModel):
    customer_id: str
    channel: str = Field(pattern="^(email|sms|whatsapp|analytics)$")
    purpose: str = Field(min_length=2, max_length=60)
    granted: bool
    source: str = Field(default="admin", max_length=60)


class NotificationIn(BaseModel):
    customer_id: str | None = None
    channel: str = Field(pattern="^(email|sms|whatsapp|push)$")
    recipient: str = Field(min_length=3, max_length=255)
    template_key: str = Field(min_length=2, max_length=80)
    payload: dict = Field(default_factory=dict)


@crm_router.get("/leads")
def list_leads(db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.SALES, UserRole.AUDITOR))) -> list[dict]:
    rows = db.scalars(select(Lead).where(Lead.tenant_id == user.tenant_id).order_by(Lead.created_at.desc())).all()
    return [{"id": row.id, "full_name": row.full_name, "email": row.email, "phone": row.phone, "source": row.source, "status": row.status, "owner_user_id": row.owner_user_id} for row in rows]


@crm_router.post("/leads", status_code=201)
def create_lead(payload: LeadIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.SALES))) -> dict:
    row = Lead(tenant_id=user.tenant_id, owner_user_id=user.id, **payload.model_dump())
    db.add(row)
    db.flush()
    AuditService.record(db, user, "crm.lead.created", "lead", row.id, {"source": row.source})
    db.commit()
    return {"id": row.id, "status": row.status}


@crm_router.post("/opportunities", status_code=201)
def create_opportunity(payload: OpportunityIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.SALES))) -> dict:
    if payload.customer_id and not db.scalar(select(Customer.id).where(Customer.id == payload.customer_id, Customer.tenant_id == user.tenant_id)):
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if payload.lead_id and not db.scalar(select(Lead.id).where(Lead.id == payload.lead_id, Lead.tenant_id == user.tenant_id)):
        raise HTTPException(status_code=404, detail="Lead no encontrado")
    row = Opportunity(tenant_id=user.tenant_id, owner_user_id=user.id, **payload.model_dump())
    db.add(row)
    db.flush()
    AuditService.record(db, user, "crm.opportunity.created", "opportunity", row.id, {"value": str(row.expected_value)})
    db.commit()
    return {"id": row.id, "stage": row.stage, "expected_value": str(row.expected_value)}


@crm_router.put("/opportunities/{opportunity_id}/stage")
def change_stage(opportunity_id: str, payload: OpportunityStageIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.SALES))) -> dict:
    row = db.scalar(select(Opportunity).where(Opportunity.id == opportunity_id, Opportunity.tenant_id == user.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Oportunidad no encontrada")
    row.stage = payload.stage
    AuditService.record(db, user, "crm.opportunity.stage", "opportunity", row.id, {"stage": row.stage})
    db.commit()
    return {"id": row.id, "stage": row.stage}


@loyalty_router.post("/entries", status_code=201)
def add_loyalty(payload: LoyaltyIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.CASHIER, UserRole.SALES))) -> dict:
    customer = db.scalar(select(Customer).where(Customer.id == payload.customer_id, Customer.tenant_id == user.tenant_id))
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    new_balance = Decimal(customer.loyalty_points) + payload.points_delta
    if new_balance < 0:
        raise HTTPException(status_code=409, detail="Puntos insuficientes")
    entry = LoyaltyEntry(tenant_id=user.tenant_id, created_by_user_id=user.id, **payload.model_dump())
    db.add(entry)
    customer.loyalty_points = new_balance
    AuditService.record(db, user, "loyalty.changed", "customer", customer.id, {"delta": str(payload.points_delta), "balance": str(new_balance)})
    db.commit()
    return {"entry_id": entry.id, "customer_id": customer.id, "points": str(customer.loyalty_points)}


@loyalty_router.put("/consents")
def upsert_consent(payload: ConsentIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.CASHIER, UserRole.SALES))) -> dict:
    if not db.scalar(select(Customer.id).where(Customer.id == payload.customer_id, Customer.tenant_id == user.tenant_id)):
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    row = db.scalar(select(Consent).where(Consent.tenant_id == user.tenant_id, Consent.customer_id == payload.customer_id, Consent.channel == payload.channel, Consent.purpose == payload.purpose))
    if row is None:
        row = Consent(tenant_id=user.tenant_id, **payload.model_dump())
        db.add(row)
    else:
        row.granted = payload.granted
        row.source = payload.source
    AuditService.record(db, user, "consent.changed", "customer", payload.customer_id, {"channel": payload.channel, "purpose": payload.purpose, "granted": payload.granted})
    db.commit()
    return {"customer_id": payload.customer_id, "channel": payload.channel, "purpose": payload.purpose, "granted": row.granted}


@notification_router.post("", status_code=201)
def queue_notification(payload: NotificationIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.SALES, UserRole.SUPPORT))) -> dict:
    if payload.customer_id:
        consent = db.scalar(select(Consent).where(Consent.tenant_id == user.tenant_id, Consent.customer_id == payload.customer_id, Consent.channel == payload.channel, Consent.purpose == "marketing", Consent.granted.is_(True)))
        if payload.template_key.startswith("marketing.") and consent is None:
            raise HTTPException(status_code=409, detail="No existe consentimiento para marketing en este canal")
    row = Notification(tenant_id=user.tenant_id, customer_id=payload.customer_id, channel=payload.channel, recipient=payload.recipient, template_key=payload.template_key, payload_json=json.dumps(payload.payload, ensure_ascii=False))
    db.add(row)
    db.flush()
    AuditService.record(db, user, "notification.queued", "notification", row.id, {"channel": row.channel, "template": row.template_key})
    db.commit()
    return {"id": row.id, "status": row.status}
