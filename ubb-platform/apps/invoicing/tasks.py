import logging

from celery import shared_task

from apps.platform.customers.models import TopUpAttempt
from apps.usage.models import Invoice

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_invoicing")
def reconcile_missing_receipts():
    """Create receipt invoices for completed top-ups that are missing receipts.

    Catches transient Stripe failures during receipt generation.
    Runs hourly — fast no-op when no missing receipts.
    """
    from apps.invoicing.services import ReceiptService

    # Find succeeded top-up attempts with no corresponding Invoice
    attempts = TopUpAttempt.objects.filter(
        status="succeeded",
    ).exclude(
        id__in=Invoice.objects.values_list("top_up_attempt_id", flat=True),
    ).select_related("customer__tenant")

    for attempt in attempts:
        try:
            ReceiptService.create_topup_receipt(attempt.customer, attempt)
            logger.info(
                "Reconciled missing receipt",
                extra={"data": {"attempt_id": str(attempt.id)}},
            )
        except Exception:
            logger.exception(
                "Failed to reconcile missing receipt",
                extra={"data": {"attempt_id": str(attempt.id)}},
            )
