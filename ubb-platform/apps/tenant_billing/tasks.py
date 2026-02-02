import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.tenant_billing.models import TenantBillingPeriod, TenantInvoice
from apps.tenant_billing.services import TenantBillingService

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_billing")
def close_tenant_billing_periods():
    """Close all open billing periods from previous months."""
    today = timezone.now().date()
    first_of_month = today.replace(day=1)

    periods = TenantBillingPeriod.objects.filter(
        status="open",
        period_end__lte=first_of_month,
    ).select_related("tenant")

    for period in periods:
        try:
            TenantBillingService.close_period(period)
            logger.info(
                "Closed tenant billing period",
                extra={"data": {"period_id": str(period.id), "tenant": period.tenant.name}},
            )
        except Exception:
            logger.exception(
                "Failed to close tenant billing period",
                extra={"data": {"period_id": str(period.id)}},
            )


@shared_task(queue="ubb_billing")
def generate_tenant_platform_invoices():
    """Generate Stripe invoices for closed billing periods without invoices."""
    periods = TenantBillingPeriod.objects.filter(
        status="closed",
    ).filter(
        invoice__isnull=True,
    ).select_related("tenant")

    for period in periods:
        if period.platform_fee_micros <= 0:
            period.status = "invoiced"
            period.save(update_fields=["status", "updated_at"])
            continue

        try:
            _create_tenant_invoice(period)
        except Exception:
            logger.exception(
                "Failed to create tenant platform invoice",
                extra={"data": {"period_id": str(period.id)}},
            )


@transaction.atomic
def _create_tenant_invoice(period):
    """Create a platform fee invoice for a tenant.

    On Stripe failure: period stays "closed" so the next scheduled run retries.
    On success: period moves to "invoiced".
    """
    period = TenantBillingPeriod.objects.select_for_update().get(pk=period.pk)
    if period.status != "closed":
        return

    # Idempotency: skip if invoice already exists
    if TenantInvoice.objects.filter(billing_period=period).exists():
        return

    # TODO: Stripe integration added in Task 10.
    # For now, create local record as draft.
    invoice = TenantInvoice.objects.create(
        tenant=period.tenant,
        billing_period=period,
        total_amount_micros=period.platform_fee_micros,
        status="draft",
    )

    period.status = "invoiced"
    period.save(update_fields=["status", "updated_at"])

    logger.info(
        "Created tenant platform invoice",
        extra={"data": {
            "invoice_id": str(invoice.id),
            "tenant": period.tenant.name,
            "amount_micros": period.platform_fee_micros,
        }},
    )
