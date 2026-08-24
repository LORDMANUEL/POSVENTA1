import hashlib
import hmac

from app.payment_gateway import SandboxPaymentAdapter


def test_sandbox_payment_intent_is_deterministic_for_same_idempotency_key() -> None:
    adapter = SandboxPaymentAdapter(webhook_secret="sandbox-secret")

    first = adapter.create_intent(
        tenant_id="tenant-1",
        order_id="order-1",
        amount="125.50",
        idempotency_key="checkout-key-001",
    )
    repeated = adapter.create_intent(
        tenant_id="tenant-1",
        order_id="order-1",
        amount="125.50",
        idempotency_key="checkout-key-001",
    )

    assert first == repeated
    assert first.provider == "sandbox"
    assert first.status == "pending"
    assert first.reference.startswith("mz_sandbox_")


def test_sandbox_webhook_signature_is_verified() -> None:
    secret = "sandbox-secret"
    adapter = SandboxPaymentAdapter(webhook_secret=secret)
    body = b'{"provider_reference":"mz_sandbox_abc","status":"paid"}'
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert adapter.verify_webhook(body, signature) is True
    assert adapter.verify_webhook(body, "deadbeef") is False
