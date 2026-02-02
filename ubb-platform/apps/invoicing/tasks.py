import logging

from django.utils import timezone
from django.db import transaction
from celery import shared_task

from apps.usage.models import BillingPeriod, UsageEvent, Invoice
from apps.stripe_integration.services.stripe_service import StripeService
from core.exceptions import StripeFatalError

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_invoicing", acks_late=True)
def generate_weekly_invoices():
    """Find all open billing periods that have ended and generate invoices."""
    now = timezone.now()
    periods = BillingPeriod.objects.filter(
        status="open", period_end__lte=now
    ).select_related("customer", "tenant")
    for period in periods:
        try:
            _invoice_period(period)
        except StripeFatalError:
            logger.exception(
                "Fatal Stripe error invoicing period, requires manual intervention",
                extra={"data": {"period_id": str(period.id)}},
            )
        except Exception:
            logger.exception(
                "Failed to invoice period",
                extra={"data": {"period_id": str(period.id)}},
            )


@transaction.atomic
def _invoice_period(period):
    period = BillingPeriod.objects.select_for_update().get(pk=period.pk)
    if period.status != "open":
        return

    customer = period.customer
    events = list(UsageEvent.objects.filter(
        customer=customer,
        tenant=period.tenant,
        effective_at__gte=period.period_start,
        effective_at__lt=period.period_end,
        invoice__isnull=True,
    ))

    if not events:
        period.status = "closed"
        period.save(update_fields=["status", "updated_at"])
        return

    total_micros = sum(e.cost_micros for e in events)

    # StripeService handles idempotency keys and attempt counting internally
    stripe_invoice_id = StripeService.create_invoice_with_line_items(
        customer=customer,
        billing_period=period,
        usage_events=events,
    )

    invoice = Invoice.objects.create(
        tenant=period.tenant,
        customer=customer,
        billing_period=period,
        stripe_invoice_id=stripe_invoice_id,
        total_amount_micros=total_micros,
        status="finalized",
        finalized_at=timezone.now(),
    )

    # Link usage events ONLY after finalize succeeded
    UsageEvent.objects.filter(id__in=[e.id for e in events]).update(invoice=invoice)

    period.status = "invoiced"
    period.total_cost_micros = total_micros
    period.event_count = len(events)
    period.save(update_fields=["status", "total_cost_micros", "event_count", "updated_at"])
