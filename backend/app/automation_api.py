import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .automation_models import OutboxEvent, WorkflowDefinition, WorkflowRun
from .db import get_db
from .models import User, UserRole
from .module_api import require_enabled_module
from .security import require_roles
from .services import AuditService

workflow_router = APIRouter(prefix="/workflows", tags=["workflows"], dependencies=[Depends(require_enabled_module("workflows"))])
integration_router = APIRouter(prefix="/integrations", tags=["integrations"], dependencies=[Depends(require_enabled_module("integrations"))])


class WorkflowIn(BaseModel):
    key: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=2, max_length=180)
    event_key: str = Field(min_length=2, max_length=100)
    condition: dict = Field(default_factory=dict)
    action: dict = Field(default_factory=dict)


class WorkflowRunIn(BaseModel):
    event_key: str = Field(min_length=2, max_length=100)
    payload: dict = Field(default_factory=dict)


class OutboxIn(BaseModel):
    topic: str = Field(min_length=2, max_length=100)
    payload: dict = Field(default_factory=dict)
    event_id: str | None = Field(default=None, max_length=64)


@workflow_router.get("")
def list_workflows(db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.AUDITOR))) -> list[dict]:
    rows = db.scalars(select(WorkflowDefinition).where(WorkflowDefinition.tenant_id == user.tenant_id).order_by(WorkflowDefinition.name)).all()
    return [{"id": row.id, "key": row.key, "name": row.name, "event_key": row.event_key, "active": row.active} for row in rows]


@workflow_router.post("", status_code=201)
def create_workflow(payload: WorkflowIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN))) -> dict:
    if db.scalar(select(WorkflowDefinition.id).where(WorkflowDefinition.tenant_id == user.tenant_id, WorkflowDefinition.key == payload.key)):
        raise HTTPException(status_code=409, detail="Workflow ya registrado")
    row = WorkflowDefinition(tenant_id=user.tenant_id, key=payload.key, name=payload.name, event_key=payload.event_key, condition_json=json.dumps(payload.condition, ensure_ascii=False), action_json=json.dumps(payload.action, ensure_ascii=False))
    db.add(row)
    db.flush()
    AuditService.record(db, user, "workflow.created", "workflow", row.id, {"key": row.key})
    db.commit()
    return {"id": row.id, "key": row.key, "active": row.active}


@workflow_router.post("/dispatch", status_code=202)
def dispatch_event(payload: WorkflowRunIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.SUPPORT))) -> dict:
    workflows = db.scalars(select(WorkflowDefinition).where(WorkflowDefinition.tenant_id == user.tenant_id, WorkflowDefinition.event_key == payload.event_key, WorkflowDefinition.active.is_(True))).all()
    runs = []
    for workflow in workflows:
        run = WorkflowRun(tenant_id=user.tenant_id, workflow_id=workflow.id, event_key=payload.event_key, event_payload_json=json.dumps(payload.payload, ensure_ascii=False))
        db.add(run)
        db.flush()
        runs.append(run.id)
    AuditService.record(db, user, "workflow.event.dispatched", "workflow_event", payload.event_key, {"runs": len(runs)})
    db.commit()
    return {"event_key": payload.event_key, "runs": runs}


@workflow_router.post("/runs/{run_id}/complete")
def complete_run(run_id: str, success: bool, result: str = "{}", error: str | None = None, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.SUPPORT))) -> dict:
    row = db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id, WorkflowRun.tenant_id == user.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada")
    row.status = "completed" if success else "failed"
    row.result_json = result
    row.error = error
    row.finished_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": row.id, "status": row.status}


@integration_router.post("/outbox", status_code=201)
def enqueue_outbox(payload: OutboxIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.SUPPORT))) -> dict:
    event_id = payload.event_id or str(uuid.uuid4())
    existing = db.scalar(select(OutboxEvent).where(OutboxEvent.tenant_id == user.tenant_id, OutboxEvent.event_id == event_id))
    if existing:
        return {"id": existing.id, "event_id": existing.event_id, "status": existing.status}
    row = OutboxEvent(tenant_id=user.tenant_id, event_id=event_id, topic=payload.topic, payload_json=json.dumps(payload.payload, ensure_ascii=False))
    db.add(row)
    db.flush()
    AuditService.record(db, user, "outbox.enqueued", "outbox_event", row.id, {"topic": row.topic})
    db.commit()
    return {"id": row.id, "event_id": row.event_id, "status": row.status}


@integration_router.post("/outbox/{event_id}/ack")
def acknowledge_outbox(event_id: str, success: bool, error: str | None = None, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.SUPPORT))) -> dict:
    row = db.scalar(select(OutboxEvent).where(OutboxEvent.event_id == event_id, OutboxEvent.tenant_id == user.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    row.attempts += 1
    row.status = "delivered" if success else "failed"
    row.last_error = error
    if success:
        row.delivered_at = datetime.now(timezone.utc)
    db.commit()
    return {"event_id": row.event_id, "status": row.status, "attempts": row.attempts}
