import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.billing.tenant_billing.models import TenantBillingPeriod, TenantInvoice
from apps.billing.tenant_billing.services import TenantBillingService

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
def reconcile_tenant_billing_periods():
    """Reconcile all open billing periods against actual UsageEvent data.

    Catches any accumulate_usage drift from transient failures.
    Runs hourly — fast no-op when totals match.
    """
    periods = TenantBillingPeriod.objects.filter(
        status="open",
    ).select_related("tenant")

    for period in periods:
        try:
            TenantBillingService.reconcile_period(period)
        except Exception:
            logger.exception(
                "Failed to reconcile tenant billing period",
                extra={"data": {"period_id": str(period.id)}},
            )


@shared_task(queue="ubb_billing")
def generate_tenant_platform_invoices():
    """Generate Stripe invoices for closed billing periods without invoices.

    Also reclaims stale 'invoicing' periods (stuck >30 min) by reverting to 'closed'.
    """
    from datetime import timedelta

    stale_cutoff = timezone.now() - timedelta(minutes=30)

    # Reclaim stale invoicing periods (worker crash recovery)
    stale_count = TenantBillingPeriod.objects.filter(
        status="invoicing",
        updated_at__lt=stale_cutoff,
    ).update(status="closed")
    if stale_count:
        logger.warning(
            "Reclaimed stale invoicing periods",
            extra={"data": {"count": stale_count}},
        )

    periods = TenantBillingPeriod.objects.filter(
        status="closed",
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


def _create_tenant_invoice(period):
    """Create a platform fee invoice for a tenant (two-phase).

    Phase 1: Claim period with 'invoicing' status inside a transaction.
    Phase 2: Call Stripe outside any transaction (no DB locks held).
    Phase 3: Record result in a new transaction.

    On Stripe failure: period stays 'invoicing', next run can reclaim stale ones.
    On success: local TenantInvoice created, period moves to 'invoiced'.
    """
    # Phase 1 — Claim the period
    with transaction.atomic():
        period = TenantBillingPeriod.objects.select_for_update().get(pk=period.pk)
        if period.status != "closed":
            return

        if TenantInvoice.objects.filter(billing_period=period).exists():
            period.status = "invoiced"
            period.save(update_fields=["status", "updated_at"])
            return

        period.status = "invoicing"
        period.save(update_fields=["status", "updated_at"])

    # Phase 2 — Call Stripe (no DB transaction held)
    from apps.billing.stripe.services.stripe_service import StripeService

    try:
        stripe_invoice_id = StripeService.create_tenant_platform_invoice(
            period.tenant, period
        )
    except Exception:
        # Stripe failed — revert to closed so next run retries
        TenantBillingPeriod.objects.filter(
            id=period.id, status="invoicing"
        ).update(status="closed")
        raise

    if not stripe_invoice_id:
        TenantBillingPeriod.objects.filter(
            id=period.id, status="invoicing"
        ).update(status="closed")
        return

    # Phase 3 — Record success
    with transaction.atomic():
        period = TenantBillingPeriod.objects.select_for_update().get(pk=period.pk)
        if period.status != "invoicing":
            return  # Another process already handled it

        TenantInvoice.objects.create(
            tenant=period.tenant,
            billing_period=period,
            stripe_invoice_id=stripe_invoice_id,
            total_amount_micros=period.platform_fee_micros,
            status="finalized",
            finalized_at=timezone.now(),
        )

        period.status = "invoiced"
        period.save(update_fields=["status", "updated_at"])

    logger.info(
        "Created tenant platform invoice",
        extra={"data": {
            "invoice_id": stripe_invoice_id,
            "tenant": period.tenant.name,
            "amount_micros": period.platform_fee_micros,
        }},
    )
