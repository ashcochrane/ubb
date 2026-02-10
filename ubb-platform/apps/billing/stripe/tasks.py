import logging

from celery import shared_task
from datetime import timedelta
from django.db import transaction
from django.utils import timezone

from core.exceptions import StripeTransientError, StripePaymentError, StripeFatalError
from core.locking import lock_for_billing, lock_top_up_attempt

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

    Moved from apps.metering.usage.tasks to apps.billing.stripe.tasks
    to respect product isolation boundaries.
    """
    from apps.billing.topups.models import TopUpAttempt
    from apps.billing.stripe.services.stripe_service import StripeService

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
        charge_result = StripeService.charge_saved_payment_method(
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
            attempt.save(update_fields=[
                "status", "stripe_payment_intent_id", "updated_at"
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


@shared_task(queue="ubb_webhooks")
def cleanup_webhook_events():
    """Batch-delete old webhook events to avoid long-running deletes and WAL bloat."""
    from apps.billing.stripe.models import StripeWebhookEvent

    now = timezone.now()
    succeeded_cutoff = now - timedelta(days=90)
    failed_cutoff = now - timedelta(days=180)

    # Delete succeeded/skipped events older than 90 days in batches
    _batched_delete(
        StripeWebhookEvent.objects.filter(
            status__in=["succeeded", "skipped"],
            created_at__lt=succeeded_cutoff,
        )
    )

    # Delete failed events older than 180 days in batches
    _batched_delete(
        StripeWebhookEvent.objects.filter(
            status="failed",
            created_at__lt=failed_cutoff,
        )
    )


def _batched_delete(queryset, batch_size=1000):
    """Delete in batches by PK range to avoid long locks."""
    while True:
        batch_ids = list(queryset.values_list("id", flat=True)[:batch_size])
        if not batch_ids:
            break
        deleted, _ = queryset.model.objects.filter(id__in=batch_ids).delete()
        logger.info(
            "Cleaned up webhook events",
            extra={"data": {"deleted_count": deleted}},
        )
