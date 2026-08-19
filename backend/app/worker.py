from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .automation_models import OutboxEvent, WorkflowDefinition, WorkflowRun
from .config import get_settings
from .db import SessionLocal

settings = get_settings()


def _json_object(raw: str, label: str) -> dict:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} no contiene JSON válido") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} debe ser un objeto JSON")
    return value


def process_workflow_once(db: Session) -> bool:
    run = db.scalar(
        select(WorkflowRun)
        .where(WorkflowRun.status == "queued")
        .order_by(WorkflowRun.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if run is None:
        return False
    workflow = db.scalar(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == run.workflow_id,
            WorkflowDefinition.tenant_id == run.tenant_id,
            WorkflowDefinition.active.is_(True),
        )
    )
    if workflow is None:
        run.status = "failed"
        run.error = "Workflow no existe o está inactivo"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        return True

    run.status = "running"
    db.flush()
    try:
        action = _json_object(workflow.action_json, "action_json")
        event_payload = _json_object(run.event_payload_json, "event_payload_json")
        action_type = str(action.get("type", "")).strip()
        if action_type != "outbox":
            raise ValueError(f"Acción no soportada por worker: {action_type or '<vacía>'}")
        topic = str(action.get("topic", "")).strip()
        if not topic:
            raise ValueError("La acción outbox requiere topic")
        static_payload = action.get("payload", {})
        if static_payload is None:
            static_payload = {}
        if not isinstance(static_payload, dict):
            raise ValueError("action.payload debe ser objeto")
        payload = {**static_payload, "event": event_payload}
        event_id = f"workflow:{run.id}"
        existing = db.scalar(
            select(OutboxEvent).where(
                OutboxEvent.tenant_id == run.tenant_id,
                OutboxEvent.event_id == event_id,
            )
        )
        if existing is None:
            db.add(
                OutboxEvent(
                    tenant_id=run.tenant_id,
                    event_id=event_id,
                    topic=topic,
                    payload_json=json.dumps(payload, ensure_ascii=False),
                )
            )
        run.status = "completed"
        run.result_json = json.dumps({"outbox_event_id": event_id, "topic": topic}, ensure_ascii=False)
        run.error = None
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        failed = db.scalar(select(WorkflowRun).where(WorkflowRun.id == run.id).with_for_update())
        if failed is not None:
            failed.status = "failed"
            failed.error = str(exc)[:2000]
            failed.finished_at = datetime.now(timezone.utc)
            db.commit()
    return True


def _backoff(attempts: int) -> timedelta:
    seconds = min(3600, max(5, 2 ** min(attempts, 10)))
    return timedelta(seconds=seconds)


def _deliver_http(event: OutboxEvent, target: str) -> None:
    body = event.payload_json.encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mily-Zebra-Outbox/1.0",
        "X-Mily-Event-ID": event.event_id,
        "X-Mily-Topic": event.topic,
    }
    if settings.outbox_hmac_secret:
        signature = hmac.new(
            settings.outbox_hmac_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        headers["X-Mily-Signature-SHA256"] = signature
    request = urllib.request.Request(target, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=settings.outbox_timeout_seconds) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"Destino devolvió HTTP {response.status}")


def process_outbox_once(db: Session) -> bool:
    now = datetime.now(timezone.utc)
    event = db.scalar(
        select(OutboxEvent)
        .where(
            OutboxEvent.status.in_(["pending", "failed"]),
            or_(OutboxEvent.next_attempt_at.is_(None), OutboxEvent.next_attempt_at <= now),
        )
        .order_by(OutboxEvent.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if event is None:
        return False
    event.attempts += 1
    target = settings.outbox_targets.get(event.topic)
    if not target:
        event.status = "failed"
        event.last_error = f"No hay destino configurado para topic '{event.topic}'"
        event.next_attempt_at = now + _backoff(event.attempts)
        db.commit()
        return True
    try:
        _deliver_http(event, target)
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
        event.status = "failed"
        event.last_error = str(exc)[:2000]
        event.next_attempt_at = now + _backoff(event.attempts)
        db.commit()
        return True
    event.status = "delivered"
    event.last_error = None
    event.next_attempt_at = None
    event.delivered_at = now
    db.commit()
    return True


def run_cycle() -> bool:
    worked = False
    with SessionLocal() as db:
        worked = process_workflow_once(db) or worked
    with SessionLocal() as db:
        worked = process_outbox_once(db) or worked
    return worked


def main() -> None:
    print("Mily Zebra worker iniciado", flush=True)
    while True:
        try:
            worked = run_cycle()
        except Exception as exc:  # defensive process boundary; individual jobs are handled above.
            print(f"[worker] error inesperado: {exc}", flush=True)
            worked = False
        if not worked:
            time.sleep(max(0.5, settings.worker_poll_seconds))


if __name__ == "__main__":
    main()
