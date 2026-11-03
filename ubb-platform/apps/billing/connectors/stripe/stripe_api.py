"""Customer-facing Stripe API operations.

These are part of the Stripe connector — they operate on the tenant's
Stripe Connected Account to handle customer-facing payments.
"""
import stripe
from django.conf import settings

from apps.billing.stripe.services.stripe_service import (
    api_key_for_tenant,
    field,
    stripe_call,
    validate_amount_micros,
    micros_to_cents,
)
from apps.billing.locking import (
    the_currency_a_top_up_credits, the_currency_a_top_up_will_credit)
from core.currency_policy import the_rails_currency
from core.exceptions import (
    PaymentNotAvailable, StripeFatalError, StripeNotConfigured, StripeTransientError)
from apps.platform.queries import get_customer_stripe_id, get_tenant_stripe_account
from apps.platform.tenants.models import refuse_a_rail_operation_while_it_is_closed
from core.problems import Problem

stripe.api_key = settings.STRIPE_SECRET_KEY


def _charges_ready(tenant_id) -> bool:
    """True only if the tenant has a connected account that is charge-ready.

    Guards every customer-facing charge so UBB never charges a connected account
    that Stripe has not enabled for charges.
    """
    from apps.platform.tenants.models import Tenant
    return Tenant.objects.filter(
        id=tenant_id, charges_enabled=True,
    ).exclude(stripe_connected_account_id="").exists()


def refuse_a_checkout_that_cannot_proceed(customer, amount_micros, *, owner_id):
    """EVERY KNOWABLE PRECONDITION OF A TOP-UP CHECKOUT, asked before the
    attempt exists (R10 Stage C1b, F-11 + O-6, RULED Q2). The top-up door
    (``api/v1/topups.py``) calls this BEFORE it writes the ``TopUpAttempt``
    and its audit row, so a refusal leaves nothing pending behind; the
    checkout call below asks the same questions again on its own, so the
    connector refuses correctly whoever calls it. Each refusal is its
    truthful registered problem (RULED Q21):

    - an invalid amount → ``validation_error`` (the request schema already
      refuses one; this is the rule, asked at the money boundary);
    - a closed rail → ``payment_rail_not_activated`` (``PaymentRailClosed``);
    - a currency the wallet does not share with the rail →
      ``unsupported_currency`` (``CurrencyDisagreement``), never collapsed
      into payment availability;
    - no connected account, or one not charge-ready →
      ``payment_not_available`` (``PaymentNotAvailable``, 409);
    - no server Stripe key for the tenant's mode → ``service_unavailable``
      (503): the service is not configured to perform the payment, which is
      not the tenant's state and not the customer's request.

    Returns ``(currency, amount_cents, connected_account, api_key)`` for the
    call that follows.
    """
    try:
        validate_amount_micros(amount_micros)
    except StripeFatalError as exc:
        raise Problem("validation_error", str(exc)) from exc
    # G27's flag, operationally: no new money on a closed rail.
    refuse_a_rail_operation_while_it_is_closed(customer.tenant)
    # The currency is the wallet's this top-up credits, never a literal
    # (#565): refused here, before anything is sent, if that record is not
    # in UBB's one currency.
    currency = the_rails_currency(*the_currency_a_top_up_will_credit(owner_id))
    try:
        amount_cents = micros_to_cents(amount_micros, currency)
    except StripeFatalError as exc:
        raise Problem("validation_error", str(exc)) from exc
    connected_account = get_tenant_stripe_account(customer.tenant_id)
    if not connected_account:
        raise PaymentNotAvailable(
            tenant_id=customer.tenant_id, reason="no connected Stripe account")
    if not _charges_ready(customer.tenant_id):
        raise PaymentNotAvailable(
            tenant_id=customer.tenant_id,
            reason="the connected Stripe account is not charge-ready (charges_enabled=False)")
    # A sandbox tenant with no (or a live) STRIPE_TEST_SECRET_KEY raises
    # StripeNotConfigured itself; an unset live key is the same refusal.
    api_key = api_key_for_tenant(customer.tenant)
    if not api_key:
        raise StripeNotConfigured(
            "Stripe API key is not configured. "
            "Set STRIPE_SECRET_KEY in the environment to enable Stripe operations.")
    return currency, amount_cents, connected_account, api_key


def create_checkout_session(customer, amount_micros, top_up_attempt, *, success_url, cancel_url):
    """Create Stripe Checkout session for top-up.

    F5.3 guard: NEVER pass automatic_tax here (even when the tenant has
    automatic_tax_enabled). A top-up funds a wallet — the credited micros
    must equal the charged amount exactly; tax on top would either skew the
    wallet ledger or charge the customer more than gets credited. Tax applies
    only where Stripe bills for consumption (subscriptions, usage invoices).
    """
    owner_id = (top_up_attempt.billing_owner_id
                or top_up_attempt.customer.resolve_billing_owner().id)
    currency, amount_cents, connected_account, api_key = (
        refuse_a_checkout_that_cannot_proceed(customer, amount_micros, owner_id=owner_id))
    customer_stripe_id = get_customer_stripe_id(customer.id)

    session = stripe_call(
        stripe.checkout.Session.create,
        api_key=api_key,
        retryable=True,
        idempotency_key=f"checkout-{top_up_attempt.id}",
        customer=customer_stripe_id,
        client_reference_id=str(top_up_attempt.id),
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": currency,
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

    F5.3 guard: NEVER pass automatic_tax on this PaymentIntent — wallet
    credit must equal the charged amount exactly (see create_checkout_session).
    """
    validate_amount_micros(amount_micros)
    # G27's flag, operationally — as for the Checkout above.
    refuse_a_rail_operation_while_it_is_closed(customer.tenant)
    # The wallet's currency, as for the Checkout above (#565).
    currency = the_rails_currency(*the_currency_a_top_up_credits(top_up_attempt))
    amount_cents = micros_to_cents(amount_micros, currency)
    customer_stripe_id = get_customer_stripe_id(customer.id)
    connected_account = get_tenant_stripe_account(customer.tenant_id)
    if not connected_account or not _charges_ready(customer.tenant_id):
        return None  # Connected account not charge-ready -- skip (mirror no-PM skip)

    api_key = api_key_for_tenant(customer.tenant)

    payment_methods = stripe_call(
        stripe.PaymentMethod.list,
        api_key=api_key,
        retryable=True,
        idempotency_key=None,  # list is naturally idempotent
        customer=customer_stripe_id,
        type="card",
        stripe_account=connected_account,
    )
    if not payment_methods.data:
        return None

    # The customer's default: the real shape is
    # ``cust.invoice_settings.default_payment_method`` (a StripeObject holding
    # an id, or an expanded PaymentMethod); a dict-style read raised and was
    # swallowed into "charge the first listed card" (F-3a). A Stripe failure
    # on this read still degrades to the first listed card — the charge
    # itself is what must not silently change.
    default_pm = None
    try:
        cust = stripe_call(stripe.Customer.retrieve, api_key=api_key,
                           retryable=True, idempotency_key=None,
                           id=customer_stripe_id, stripe_account=connected_account)
    except (StripeTransientError, StripeFatalError, stripe.error.StripeError):
        cust = None
    default_pm = field(field(cust, "invoice_settings"), "default_payment_method")
    if default_pm is not None and not isinstance(default_pm, str):
        default_pm = field(default_pm, "id")
    pm_id = default_pm or payment_methods.data[0].id

    intent = stripe_call(
        stripe.PaymentIntent.create,
        api_key=api_key,
        retryable=True,
        idempotency_key=f"charge-{top_up_attempt.id}",
        customer=customer_stripe_id,
        amount=amount_cents,
        currency=currency,
        payment_method=pm_id,
        off_session=True,
        confirm=True,
        metadata={"topup_attempt_id": str(top_up_attempt.id)},
        stripe_account=connected_account,
    )
    return intent
