from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Branch


def _canonical(value: Any) -> Any:
    if isinstance(value, Decimal):
        normalized = value.normalize()
        return format(normalized, "f")
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def canonical_request_hash(value: Any) -> str:
    payload = json.dumps(
        _canonical(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def require_idempotency_match(stored_hash: str | None, incoming_hash: str) -> None:
    # Legacy records created before v0.12.1 do not have a fingerprint. They stay
    # replayable by key for backwards compatibility, but every new write stores one.
    if stored_hash and stored_hash != incoming_hash:
        raise HTTPException(
            status_code=409,
            detail="Idempotency-Key ya utilizada con una operación diferente",
        )


def require_branch_scope(
    db: Session,
    tenant_id: str,
    branch_id: str,
    *,
    active_only: bool = False,
) -> Branch:
    query = select(Branch).where(Branch.id == branch_id, Branch.tenant_id == tenant_id)
    if active_only:
        query = query.where(Branch.active.is_(True))
    branch = db.scalar(query)
    if branch is None:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    return branch
