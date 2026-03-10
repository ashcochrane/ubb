"""Customer-facing Stripe API operations.

These are part of the Stripe connector — they operate on the tenant's
Stripe Connected Account to handle customer-facing payments.
"""
import stripe
from django.conf import settings

from apps.billing.stripe.services.stripe_service import (
    stripe_call,
    validate_amount_micros,
    micros_to_cents,
)
from apps.platform.queries import get_customer_stripe_id, get_tenant_stripe_account

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_checkout_session(customer, amount_micros, top_up_attempt, *, success_url, cancel_url):
    """Create Stripe Checkout session for top-up."""
    validate_amount_micros(amount_micros)
    amount_cents = micros_to_cents(amount_micros)
    customer_stripe_id = get_customer_stripe_id(customer.id)
    connected_account = get_tenant_stripe_account(customer.tenant_id)

    session = stripe_call(
        stripe.checkout.Session.create,
        retryable=True,
        idempotency_key=f"checkout-{top_up_attempt.id}",
        customer=customer_stripe_id,
        client_reference_id=str(top_up_attempt.id),
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "unit_amount": amount_cents,
                "product_data": {"name": "Account Top-Up"},
            },
            "quantity": 1,
        }],
        success_url=success_url,
        cancel_url=cancel_url,
        stripe_account=connected_account,
    )
    top_up_attempt.stripe_checkout_session_id = session.id
    top_up_attempt.save(update_fields=["stripe_checkout_session_id", "updated_at"])
    return session.url


def charge_saved_payment_method(customer, amount_micros, top_up_attempt):
    """Charge saved payment method for top-up.

    Idempotency key derived from top_up_attempt.id — deterministic across retries.
    """
    validate_amount_micros(amount_micros)
    amount_cents = micros_to_cents(amount_micros)
    customer_stripe_id = get_customer_stripe_id(customer.id)
    connected_account = get_tenant_stripe_account(customer.tenant_id)

    payment_methods = stripe_call(
        stripe.PaymentMethod.list,
        retryable=True,
        idempotency_key=None,  # list is naturally idempotent
        customer=customer_stripe_id,
        type="card",
        stripe_account=connected_account,
    )
    if not payment_methods.data:
        return None

    intent = stripe_call(
        stripe.PaymentIntent.create,
        retryable=True,
        idempotency_key=f"charge-{top_up_attempt.id}",
        customer=customer_stripe_id,
        amount=amount_cents,
        currency="usd",
        payment_method=payment_methods.data[0].id,
        off_session=True,
        confirm=True,
        stripe_account=connected_account,
    )
    return intent
