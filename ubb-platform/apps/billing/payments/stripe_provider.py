from apps.billing.connectors.stripe.stripe_api import (
    create_checkout_session,
    charge_saved_payment_method,
)
from apps.billing.stripe.services.stripe_service import StripeService


class StripeProvider:
    """Stripe implementation of PaymentProvider protocol."""

    def create_checkout_session(
        self, customer, amount_micros, top_up_attempt, *,
        success_url, cancel_url,
    ):
        return create_checkout_session(
            customer, amount_micros, top_up_attempt,
            success_url=success_url, cancel_url=cancel_url,
        )

    def charge_saved_payment_method(self, customer, amount_micros, top_up_attempt):
        return charge_saved_payment_method(
            customer, amount_micros, top_up_attempt,
        )

    def create_platform_invoice(self, tenant, billing_period):
        return StripeService.create_tenant_platform_invoice(tenant, billing_period)

    def verify_webhook_signature(self, payload, signature, secret):
        import stripe
        return stripe.Webhook.construct_event(payload, signature, secret)
