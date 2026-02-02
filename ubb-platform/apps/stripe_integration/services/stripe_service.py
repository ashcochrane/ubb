import logging
import random
import time

import stripe
from django.conf import settings

from core.exceptions import StripeTransientError, StripePaymentError, StripeFatalError

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)


def validate_amount_micros(amount_micros):
    """Validate amount_micros > 0. Raises StripeFatalError otherwise."""
    if amount_micros is None or amount_micros <= 0:
        raise StripeFatalError(f"amount_micros must be > 0, got {amount_micros}")


def micros_to_cents(amount_micros):
    """Convert micros to cents. Raises StripeFatalError if not evenly divisible."""
    if amount_micros % 10_000 != 0:
        logger.error(
            "Non-cent-aligned amount detected",
            extra={"data": {"amount_micros": amount_micros}},
        )
        raise StripeFatalError(
            f"amount_micros={amount_micros} not divisible by 10_000"
        )
    return amount_micros // 10_000


def stripe_call(fn, *, retryable=False, idempotency_key=None, max_retries=3, **kwargs):
    """
    Wrap a Stripe API call with error mapping and optional retry.

    - retryable=True + idempotency_key: retries with exponential backoff + jitter
    - retryable=True + no key: forced to non-retryable (safety)
    - Maps Stripe exceptions to domain exceptions
    """
    if retryable and not idempotency_key:
        retryable = False

    attempts = max_retries if retryable else 1

    for attempt in range(attempts):
        try:
            if idempotency_key:
                kwargs["idempotency_key"] = idempotency_key
            return fn(**kwargs)
        except stripe.error.RateLimitError as e:
            _log_stripe_error(fn, e, attempt)
            if attempt < attempts - 1:
                _backoff(attempt)
                continue
            raise StripeTransientError(str(e)) from e
        except stripe.error.APIConnectionError as e:
            _log_stripe_error(fn, e, attempt)
            if attempt < attempts - 1:
                _backoff(attempt)
                continue
            raise StripeTransientError(str(e)) from e
        except stripe.error.APIError as e:
            _log_stripe_error(fn, e, attempt)
            if attempt < attempts - 1:
                _backoff(attempt)
                continue
            raise StripeTransientError(str(e)) from e
        except stripe.error.CardError as e:
            _log_stripe_error(fn, e, attempt)
            raise StripePaymentError(
                str(e),
                code=getattr(e, "code", None),
                decline_code=getattr(e, "decline_code", None),
            ) from e
        except stripe.error.IdempotencyError as e:
            _log_stripe_error(fn, e, attempt)
            raise StripeFatalError(str(e)) from e
        except stripe.error.AuthenticationError as e:
            _log_stripe_error(fn, e, attempt)
            raise StripeFatalError(str(e)) from e
        except stripe.error.PermissionError as e:
            _log_stripe_error(fn, e, attempt)
            raise StripeFatalError(str(e)) from e
        except stripe.error.InvalidRequestError as e:
            _log_stripe_error(fn, e, attempt)
            raise StripeFatalError(str(e)) from e


def _backoff(attempt):
    """Exponential backoff with jitter: base 0.5s, factor 2x, +/-25% jitter."""
    base = 0.5 * (2 ** attempt)
    jitter = base * 0.25 * (2 * random.random() - 1)
    delay = min(base + jitter, 10.0)
    time.sleep(delay)


def _log_stripe_error(fn, error, attempt):
    logger.warning(
        "Stripe API error",
        extra={"data": {
            "function": getattr(fn, "__name__", str(fn)),
            "error_type": type(error).__name__,
            "error_code": getattr(error, "code", None),
            "attempt": attempt + 1,
        }},
    )


class StripeService:
    @staticmethod
    def create_customer(customer):
        """Create Stripe customer under tenant's connected account. Skip if already synced."""
        if customer.stripe_customer_id:
            return customer.stripe_customer_id
        stripe_customer = stripe_call(
            stripe.Customer.create,
            retryable=True,
            idempotency_key=f"create-customer-{customer.id}",
            email=customer.email,
            metadata={"ubb_customer_id": str(customer.id), "external_id": customer.external_id},
            stripe_account=customer.tenant.stripe_connected_account_id,
        )
        customer.stripe_customer_id = stripe_customer.id
        customer.save(update_fields=["stripe_customer_id", "updated_at"])
        return stripe_customer.id

    @staticmethod
    def create_checkout_session(customer, amount_micros, top_up_attempt):
        """Create Stripe Checkout session for top-up."""
        validate_amount_micros(amount_micros)
        amount_cents = micros_to_cents(amount_micros)
        session = stripe_call(
            stripe.checkout.Session.create,
            retryable=True,
            idempotency_key=f"checkout-{top_up_attempt.id}",
            customer=customer.stripe_customer_id,
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
            success_url=settings.UBB_TOPUP_SUCCESS_URL,
            cancel_url=settings.UBB_TOPUP_CANCEL_URL,
            stripe_account=customer.tenant.stripe_connected_account_id,
        )
        top_up_attempt.stripe_checkout_session_id = session.id
        top_up_attempt.save(update_fields=["stripe_checkout_session_id", "updated_at"])
        return session.url

    @staticmethod
    def credit_customer_invoice_balance(customer, amount_micros):
        """Credit prepaid funds to Stripe customer invoice balance."""
        validate_amount_micros(amount_micros)
        amount_cents = micros_to_cents(amount_micros)
        stripe_call(
            stripe.Customer.modify,
            retryable=False,
            idempotency_key=None,  # modify has no idempotency key; not safe to retry
            id=customer.stripe_customer_id,
            balance=-amount_cents,
            stripe_account=customer.tenant.stripe_connected_account_id,
        )

    @staticmethod
    def create_invoice_with_line_items(customer, billing_period, usage_events):
        """
        Create Stripe invoice with itemized usage events.

        Idempotency:
        - Invoice: invoice-{billing_period.id}-v{attempt_number}
        - Items: invitem-{usage_event.id}-inv{stripe_invoice.id}
        - Void only on non-retryable failure, then increment attempt number.
        - Usage events marked invoiced only after finalize succeeds.
        """
        connected_account = customer.tenant.stripe_connected_account_id
        total_micros = sum(e.cost_micros for e in usage_events)
        attempt_num = billing_period.invoice_attempt_number

        if attempt_num >= 5:
            raise StripeFatalError(
                f"Invoice attempt cap reached for billing period {billing_period.id}. "
                "Manual intervention required."
            )

        invoice_idem_key = f"invoice-{billing_period.id}-v{attempt_num}"

        invoice = stripe_call(
            stripe.Invoice.create,
            retryable=True,
            idempotency_key=invoice_idem_key,
            customer=customer.stripe_customer_id,
            auto_advance=True,
            collection_method="charge_automatically",
            stripe_account=connected_account,
            application_fee_amount=StripeService._calculate_platform_fee(
                customer.tenant, total_micros
            ),
        )

        for event in usage_events:
            amount_cents = micros_to_cents(event.cost_micros)
            if amount_cents <= 0:
                logger.warning(
                    "Skipping zero-cent usage event in invoice",
                    extra={"data": {"event_id": str(event.id), "cost_micros": event.cost_micros}},
                )
                continue
            item_idem_key = f"invitem-{event.id}-inv{invoice.id}"
            stripe_call(
                stripe.InvoiceItem.create,
                retryable=True,
                idempotency_key=item_idem_key,
                customer=customer.stripe_customer_id,
                invoice=invoice.id,
                amount=amount_cents,
                currency="usd",
                description=f"Usage: {event.request_id} ({event.metadata.get('model', 'api_call')})",
                stripe_account=connected_account,
            )

        try:
            finalized = stripe_call(
                stripe.Invoice.finalize_invoice,
                retryable=True,
                idempotency_key=f"finalize-{invoice.id}",
                invoice=invoice.id,
                stripe_account=connected_account,
            )
            return finalized.id
        except StripeFatalError:
            # Non-retryable finalize failure — void and increment attempt
            try:
                stripe_call(
                    stripe.Invoice.void_invoice,
                    retryable=False,
                    invoice=invoice.id,
                    stripe_account=connected_account,
                )
            except Exception:
                logger.exception("Failed to void invoice %s", invoice.id)
            billing_period.invoice_attempt_number += 1
            billing_period.save(update_fields=["invoice_attempt_number", "updated_at"])
            raise

    @staticmethod
    def _calculate_platform_fee(tenant, total_cost_micros):
        """Calculate platform application fee in cents (rounded down)."""
        total_cents = micros_to_cents(total_cost_micros)
        fee_cents = int(total_cents * float(tenant.platform_fee_percentage) / 100)
        return fee_cents

    @staticmethod
    def charge_saved_payment_method(customer, amount_micros, top_up_attempt):
        """
        Charge saved payment method for top-up.

        Idempotency key derived from top_up_attempt.id — deterministic across retries.
        """
        validate_amount_micros(amount_micros)
        amount_cents = micros_to_cents(amount_micros)
        connected_account = customer.tenant.stripe_connected_account_id

        payment_methods = stripe_call(
            stripe.PaymentMethod.list,
            retryable=True,
            idempotency_key=None,  # list is naturally idempotent
            customer=customer.stripe_customer_id,
            type="card",
            stripe_account=connected_account,
        )
        if not payment_methods.data:
            return None

        intent = stripe_call(
            stripe.PaymentIntent.create,
            retryable=True,
            idempotency_key=f"charge-{top_up_attempt.id}",
            customer=customer.stripe_customer_id,
            amount=amount_cents,
            currency="usd",
            payment_method=payment_methods.data[0].id,
            off_session=True,
            confirm=True,
            stripe_account=connected_account,
        )
        return intent
