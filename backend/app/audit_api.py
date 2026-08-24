from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuditEvent, User, UserRole
from .security import require_roles


audit_router = APIRouter(prefix="/audit", tags=["audit"])


@audit_router.get("/events")
def list_audit_events(
    action: str | None = None,
    entity_type: str | None = None,
    actor_user_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(
            UserRole.OWNER,
            UserRole.ADMIN,
            UserRole.MANAGER,
            UserRole.AUDITOR,
            UserRole.SUPPORT,
        )
    ),
) -> list[dict]:
    query = select(AuditEvent).where(AuditEvent.tenant_id == user.tenant_id)
    if action:
        query = query.where(AuditEvent.action == action)
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type)
    if actor_user_id:
        query = query.where(AuditEvent.actor_user_id == actor_user_id)
    rows = db.scalars(
        query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit)
    ).all()

    result: list[dict] = []
    for row in rows:
        try:
            metadata = json.loads(row.metadata_json or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {"raw": row.metadata_json}
        result.append(
            {
                "id": row.id,
                "actor_user_id": row.actor_user_id,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "metadata": metadata,
                "created_at": row.created_at,
            }
        )
    return result
