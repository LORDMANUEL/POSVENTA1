from sqlalchemy import select

from app.automation_models import OutboxEvent, WorkflowRun
from app.db import SessionLocal
from app.worker import process_outbox_once, process_workflow_once


def enable(client, headers, key: str) -> None:
    response = client.put(f"/admin/modules/{key}?enabled=true", headers=headers)
    assert response.status_code == 200, response.text


def test_worker_creates_idempotent_outbox_and_never_fakes_delivery(client, owner_headers) -> None:
    enable(client, owner_headers, "workflows")
    enable(client, owner_headers, "integrations")

    workflow = client.post(
        "/workflows",
        headers=owner_headers,
        json={
            "key": "order-created-hook",
            "name": "Pedido creado a integración",
            "event_key": "order.created",
            "condition": {},
            "action": {"type": "outbox", "topic": "erp.order.created", "payload": {"source": "mily"}},
        },
    )
    assert workflow.status_code == 201, workflow.text

    dispatched = client.post(
        "/workflows/dispatch",
        headers=owner_headers,
        json={"event_key": "order.created", "payload": {"order_id": "ORDER-001"}},
    )
    assert dispatched.status_code == 202, dispatched.text
    run_id = dispatched.json()["runs"][0]

    with SessionLocal() as db:
        assert process_workflow_once(db) is True
        run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
        assert run is not None
        assert run.status == "completed"
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.event_id == f"workflow:{run_id}"))
        assert event is not None
        assert event.topic == "erp.order.created"
        assert event.status == "pending"

    with SessionLocal() as db:
        # No target is configured in tests: this must fail closed, not pretend delivery.
        assert process_outbox_once(db) is True
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.event_id == f"workflow:{run_id}"))
        assert event is not None
        assert event.status == "failed"
        assert event.attempts == 1
        assert "No hay destino configurado" in (event.last_error or "")
        assert event.delivered_at is None
