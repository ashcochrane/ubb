import logging
import time

import stripe
from celery import shared_task
from datetime import timedelta
from django.db import transaction
from django.utils import timezone

from core.exceptions import StripeTransientError, StripePaymentError, StripeFatalError
from apps.billing.locking import lock_for_billing, lock_top_up_attempt

logger = logging.getLogger(__name__)


@shared_task(
    queue="ubb_topups",
    autoretry_for=(StripeTransientError,),
    max_retries=3,
    retry_backoff=True,
    acks_late=True,
)
def charge_auto_topup_task(attempt_id):
    """
    Charge Stripe for an auto-topup attempt.

    Dispatched via transaction.on_commit after usage recording.
    Idempotent: checks attempt status before and after charging.
    """
    from apps.billing.topups.models import TopUpAttempt
    from apps.billing.connectors.stripe.stripe_api import charge_saved_payment_method

    # Pre-charge check (outside transaction — no lock needed)
    try:
        attempt = TopUpAttempt.objects.get(id=attempt_id)
    except TopUpAttempt.DoesNotExist:
        logger.warning(
            "TopUpAttempt not found, skipping",
            extra={"data": {"attempt_id": str(attempt_id)}},
        )
        return

    if attempt.status != "pending":
        logger.info(
            "TopUpAttempt already processed, skipping",
            extra={"data": {"attempt_id": str(attempt_id), "status": attempt.status}},
        )
        return

    # Charge Stripe (outside transaction — no DB locks held)
    charge_result = None
    charge_error = None
    try:
        charge_result = charge_saved_payment_method(
            attempt.customer, attempt.amount_micros, attempt
        )
    except (StripePaymentError, StripeFatalError) as e:
        charge_error = e
    # StripeTransientError propagates to Celery for autoretry

    # Post-charge update (atomic, with locks)
    with transaction.atomic():
        wallet, customer = lock_for_billing(attempt.customer_id)
        attempt = lock_top_up_attempt(attempt.id)

        if attempt.status != "pending":
            # Race: webhook or another worker already processed it
            return

        if charge_error:
            attempt.status = "failed"
            attempt.failure_reason = {
                "error_type": type(charge_error).__name__,
                "code": getattr(charge_error, "code", None),
                "decline_code": getattr(charge_error, "decline_code", None),
                "message": str(charge_error),
            }
            attempt.save(update_fields=["status", "failure_reason", "updated_at"])
            logger.warning(
                "Auto top-up charge failed",
                extra={"data": {
                    "attempt_id": str(attempt.id),
                    "customer_id": str(customer.id),
                    "error": attempt.failure_reason,
                }},
            )
            return

        if charge_result and getattr(charge_result, "status", "") == "succeeded":
            wallet.balance_micros += attempt.amount_micros
            wallet.save(update_fields=["balance_micros", "updated_at"])

            from apps.billing.wallets.models import WalletTransaction
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type="TOP_UP",
                amount_micros=attempt.amount_micros,
                balance_after_micros=wallet.balance_micros,
                description="Auto top-up",
                reference_id=str(attempt.id),
            )

            attempt.status = "succeeded"
            attempt.stripe_payment_intent_id = charge_result.id
            # Persist charge ID for reconciliation
            if hasattr(charge_result, "latest_charge") and charge_result.latest_charge:
                attempt.stripe_charge_id = (
                    charge_result.latest_charge.id
                    if hasattr(charge_result.latest_charge, "id")
                    else charge_result.latest_charge
                )
            attempt.save(update_fields=[
                "status", "stripe_payment_intent_id", "stripe_charge_id", "updated_at"
            ])

            logger.info(
                "Auto top-up succeeded",
                extra={"data": {
                    "attempt_id": str(attempt.id),
                    "customer_id": str(customer.id),
                    "amount_micros": attempt.amount_micros,
                }},
            )
        else:
            attempt.status = "failed"
            attempt.failure_reason = {
                "error_type": "NoPaymentMethod",
                "message": "No saved payment method or charge did not succeed",
            }
            attempt.save(update_fields=["status", "failure_reason", "updated_at"])


@shared_task(queue="ubb_billing")
def reconcile_topups_with_stripe():
    """Daily spot-check: compare succeeded TopUpAttempts against Stripe charges.

    Queries Stripe for each attempt with a stripe_charge_id from the last 48 hours.
    Flags mismatches (amount, status, refunds) for investigation.
    Rate-limited to avoid Stripe API limits.
    """
    from apps.billing.topups.models import TopUpAttempt

    cutoff = timezone.now() - timedelta(hours=48)

    attempts = TopUpAttempt.objects.filter(
        status="succeeded",
        stripe_charge_id__isnull=False,
        updated_at__gte=cutoff,
    ).select_related("customer__tenant")

    mismatches = 0
    for attempt in attempts.iterator():
        try:
            charge = stripe.Charge.retrieve(
                attempt.stripe_charge_id,
                stripe_account=attempt.customer.tenant.stripe_connected_account_id,
            )
        except stripe.error.StripeError:
            logger.warning("Stripe charge fetch failed", extra={"data": {
                "attempt_id": str(attempt.id), "charge_id": attempt.stripe_charge_id,
            }})
            continue

        expected_micros = attempt.amount_micros
        actual_micros = charge.amount * 10_000

        if charge.status != "succeeded" or actual_micros != expected_micros or charge.refunded:
            mismatches += 1
            logger.error("Stripe reconciliation mismatch", extra={"data": {
                "attempt_id": str(attempt.id),
                "charge_id": attempt.stripe_charge_id,
                "expected_micros": expected_micros,
                "actual_micros": actual_micros,
                "charge_status": charge.status,
                "refunded": charge.refunded,
            }})

        time.sleep(0.1)  # Rate limit: ~10 req/sec

    if mismatches > 0:
        logger.error(
            "Stripe reconciliation completed with mismatches",
            extra={"data": {"mismatch_count": mismatches}},
        )
