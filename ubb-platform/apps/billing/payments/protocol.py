from typing import Protocol, runtime_checkable


@runtime_checkable
class PaymentProvider(Protocol):
    def create_checkout_session(
        self, customer, amount_micros: int, top_up_attempt, *,
        success_url: str, cancel_url: str,
    ) -> str:
        """Create a checkout session and return the URL."""
        ...

    def charge_saved_payment_method(
        self, customer, amount_micros: int, top_up_attempt,
    ):
        """Charge the customer's saved payment method."""
        ...

    def create_platform_invoice(self, tenant, billing_period) -> str | None:
        """Create a platform invoice and return the Stripe invoice ID."""
        ...

    def verify_webhook_signature(self, payload: bytes, signature: str, secret: str) -> dict:
        """Verify and parse a webhook payload."""
        ...
