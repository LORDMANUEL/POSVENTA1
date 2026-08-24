from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PaymentIntentResult:
    provider: str
    reference: str
    status: str
    amount: str


class SandboxPaymentAdapter:
    """Deterministic software-only payment provider used for certification tests.

    This adapter never talks to a bank/acquirer and must never be presented as a
    certified real payment provider. It exists to exercise the same idempotency,
    webhook-signature and state-transition contracts a real adapter must satisfy.
    """

    provider = "sandbox"

    def __init__(self, webhook_secret: str) -> None:
        self.webhook_secret = str(webhook_secret or "")

    @staticmethod
    def _money(value: str | Decimal) -> str:
        return format(Decimal(str(value)).quantize(Decimal("0.01")), ".2f")

    def create_intent(
        self,
        *,
        tenant_id: str,
        order_id: str,
        amount: str | Decimal,
        idempotency_key: str,
    ) -> PaymentIntentResult:
        normalized_amount = self._money(amount)
        raw = "|".join(
            [
                str(tenant_id),
                str(order_id),
                normalized_amount,
                str(idempotency_key),
            ]
        ).encode("utf-8")
        reference = f"mz_sandbox_{hashlib.sha256(raw).hexdigest()[:32]}"
        return PaymentIntentResult(
            provider=self.provider,
            reference=reference,
            status="pending",
            amount=normalized_amount,
        )

    def sign_webhook(self, body: bytes) -> str:
        if not self.webhook_secret:
            raise ValueError("Sandbox webhook secret is required")
        return hmac.new(
            self.webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        if not self.webhook_secret or not signature:
            return False
        expected = self.sign_webhook(body)
        return hmac.compare_digest(expected, str(signature).strip().lower())
