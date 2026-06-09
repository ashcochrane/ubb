import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.billing.topups.models import TopUpAttempt
from apps.billing.invoicing.models import Invoice

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_invoicing")
def reconcile_missing_receipts():
    """Create receipt invoices for completed top-ups that are missing receipts.

    Catches transient Stripe failures during receipt generation.
    Runs hourly — fast no-op when no missing receipts.
    """
    from apps.billing.connectors.stripe.receipts import ReceiptService

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


def _prior_month():
    today = timezone.now().date()
    end = today.replace(day=1)  # first of THIS month (exclusive end)
    if end.month == 1:
        start = end.replace(year=end.year - 1, month=12, day=1)
    else:
        start = end.replace(month=end.month - 1, day=1)
    return start, end


@shared_task(queue="ubb_billing")
def close_postpaid_usage_periods():
    """Monthly: push each postpaid customer's prior-month usage to Stripe."""
    from apps.platform.tenants.models import Tenant
    from apps.platform.customers.models import Customer
    from apps.metering.usage.models import UsageEvent
    from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService

    start, end = _prior_month()
    for tenant in Tenant.objects.filter(billing_mode="postpaid", is_active=True):
        cust_ids = (UsageEvent.objects.filter(
            tenant=tenant, effective_at__date__gte=start, effective_at__date__lt=end)
            .values_list("customer_id", flat=True).distinct())
        targets = set()
        for c in Customer.objects.filter(id__in=list(cust_ids)):
            targets.add(c.parent_id if (c.account_type == "seat" and c.parent_id) else c.id)
        for target in Customer.objects.filter(id__in=list(targets)):
            try:
                PostpaidUsageService.push_customer_period(tenant, target, start, end)
            except Exception:
                logger.exception("postpaid.close_failed",
                                 extra={"data": {"customer_id": str(target.id)}})


@shared_task(queue="ubb_billing")
def reconcile_postpaid_usage():
    """Hourly: reclaim stale 'pushing' rows and retry 'pending'/'failed' ones."""
    from apps.billing.invoicing.models import CustomerUsageInvoice
    from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService

    stale = timezone.now() - timedelta(minutes=30)
    CustomerUsageInvoice.objects.filter(status="pushing", updated_at__lt=stale).update(status="pending")
    for rec in CustomerUsageInvoice.objects.filter(
            status__in=["pending", "failed"]).select_related("tenant", "customer"):
        try:
            PostpaidUsageService.push_customer_period(
                rec.tenant, rec.customer, rec.period_start, rec.period_end)
        except Exception:
            logger.exception("postpaid.reconcile_failed",
                             extra={"data": {"usage_invoice_id": str(rec.id)}})
