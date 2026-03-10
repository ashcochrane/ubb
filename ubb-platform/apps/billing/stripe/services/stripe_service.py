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
    if not settings.STRIPE_SECRET_KEY:
        raise StripeFatalError(
            "STRIPE_SECRET_KEY is not configured. "
            "Set it in the environment to enable Stripe operations."
        )
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
    def create_tenant_platform_invoice(tenant, billing_period):
        """
        Create a Stripe invoice for the platform fee billed directly to the tenant.

        Uses BillingTenantConfig.stripe_customer_id (tenant as UBB's customer).
        NOT on the connected account — this is UBB billing the tenant.
        auto_advance=False until items attached, then finalize explicitly.
        """
        from apps.billing.queries import get_billing_config
        billing_config = get_billing_config(tenant.id)

        if not billing_config.stripe_customer_id:
            raise StripeFatalError(
                f"Tenant {tenant.id} has no stripe_customer_id for platform billing"
            )

        amount_cents = micros_to_cents(billing_period.platform_fee_micros)
        if amount_cents <= 0:
            return None

        # Create invoice with auto_advance=False to prevent early finalization
        invoice = stripe_call(
            stripe.Invoice.create,
            retryable=True,
            idempotency_key=f"platform-invoice-{billing_period.id}",
            customer=billing_config.stripe_customer_id,
            auto_advance=False,
            collection_method="charge_automatically",
        )

        stripe_call(
            stripe.InvoiceItem.create,
            retryable=True,
            idempotency_key=f"platform-item-{billing_period.id}",
            customer=billing_config.stripe_customer_id,
            invoice=invoice.id,
            amount=amount_cents,
            currency="usd",
            description=f"UBB Platform fee: {billing_period.period_start} - {billing_period.period_end}",
        )

        finalized = stripe_call(
            stripe.Invoice.finalize_invoice,
            retryable=True,
            idempotency_key=f"platform-finalize-{billing_period.id}",
            invoice=invoice.id,
            auto_advance=True,  # Now enable auto-advance for collection
        )

        return finalized.id
