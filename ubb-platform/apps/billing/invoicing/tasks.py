import logging
import time
from datetime import timedelta

import stripe
from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.billing.topups.models import TopUpAttempt
from apps.billing.invoicing.models import Invoice
from apps.billing.stripe.services.stripe_service import stripe_call

logger = logging.getLogger(__name__)

# Stripe status -> our payment/invoice status. draft is not yet collectible (skip).
_STRIPE_STATUS_MAP = {
    "paid": "paid",
    "void": "void",
    "uncollectible": "uncollectible",
    "open": "open",
}
_TERMINAL_PAYMENT_STATUS = ("paid", "void", "uncollectible")


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
        for c in Customer.all_objects.filter(id__in=list(cust_ids)):
            targets.add(c.parent_id if (c.account_type == "seat" and c.parent_id) else c.id)
        for target in Customer.all_objects.filter(id__in=list(targets)):
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


@shared_task(queue="ubb_billing")
def reconcile_invoice_payment_status():
    """Stripe-driven repair backstop for AR invoice payment-status (Wave-5a).

    Webhooks (invoice.paid/finalized/voided/marked_uncollectible) are the fast
    path, but Stripe drops webhook retries after ~3 days; this hourly poller lists
    each charge-ready tenant's recent Stripe invoices (4-day lookback > the retry
    horizon) and repairs any local payment-status it missed.

    Reuses the api/v1 webhook helpers (_invoice_subscription_id, _refresh_urls) —
    the same lazy-import pattern apps/billing/connectors/stripe/webhooks.py uses,
    so no circular import. Status is repaired MONOTONICALLY under select_for_update:
    a terminal status (paid/void/uncollectible) never regresses. A regression Stripe
    reports against a terminal local row is loud-logged, never applied.
    """
    from apps.billing.invoicing.models import CustomerUsageInvoice
    from apps.subscriptions.models import SubscriptionInvoice
    from apps.platform.tenants.models import Tenant
    from api.v1.webhooks import _invoice_subscription_id, _refresh_urls

    cutoff = int((timezone.now() - timedelta(days=4)).timestamp())
    tenants = (Tenant.objects
               .exclude(stripe_connected_account_id="")
               .exclude(stripe_connected_account_id__isnull=True)
               .filter(charges_enabled=True))
    repaired = 0
    for tenant in tenants:
        account = tenant.stripe_connected_account_id
        try:
            invoices = stripe_call(
                stripe.Invoice.list,
                stripe_account=account,
                created={"gte": cutoff},
                limit=100,
            )
            for inv in invoices.auto_paging_iter():
                new_status = _STRIPE_STATUS_MAP.get(getattr(inv, "status", None))
                stripe_invoice_id = getattr(inv, "id", "") or ""
                if not new_status or not stripe_invoice_id:
                    continue
                if _invoice_subscription_id(inv):
                    repaired += _repair_subscription_invoice(
                        SubscriptionInvoice, tenant, stripe_invoice_id, inv,
                        new_status, _refresh_urls)
                else:
                    repaired += _repair_usage_invoice(
                        CustomerUsageInvoice, tenant, stripe_invoice_id, inv,
                        new_status, _refresh_urls)
                time.sleep(0.1)
        except Exception:
            logger.exception("ar.reconcile_failed",
                             extra={"data": {"stripe_account": account}})
            continue
    if repaired:
        logger.info("ar.reconcile_repaired", extra={"data": {"repaired": repaired}})


def _repair_usage_invoice(model, tenant, stripe_invoice_id, inv, new_status, refresh_urls):
    """Monotonically repair a CustomerUsageInvoice payment_status. Returns 1 if changed."""
    existing = model.objects.filter(
        tenant=tenant, status="pushed", stripe_invoice_id=stripe_invoice_id,
    ).exclude(stripe_invoice_id="").first()
    if not existing:
        return 0
    with transaction.atomic():
        row = model.objects.select_for_update().get(id=existing.id)
        old = row.payment_status
        if old in _TERMINAL_PAYMENT_STATUS:
            if new_status != old:
                logger.error("ar.reconcile_unexpected_regression", extra={"data": {
                    "usage_invoice_id": str(row.id), "stripe_invoice_id": stripe_invoice_id,
                    "local_status": old, "stripe_status": new_status}})
            return 0
        row.payment_status = new_status
        if new_status == "paid" and not row.paid_at:
            row.paid_at = timezone.now()
        refresh_urls(row, inv)
        row.save()
    return 1 if new_status != old else 0


def _repair_subscription_invoice(model, tenant, stripe_invoice_id, inv, new_status, refresh_urls):
    """Monotonically repair a SubscriptionInvoice status. Returns 1 if changed."""
    existing = model.objects.filter(
        tenant=tenant, stripe_invoice_id=stripe_invoice_id,
    ).first()
    if not existing:
        return 0
    with transaction.atomic():
        row = model.objects.select_for_update().get(id=existing.id)
        old = row.status
        if old in _TERMINAL_PAYMENT_STATUS:
            if new_status != old:
                logger.error("ar.reconcile_unexpected_regression", extra={"data": {
                    "subscription_invoice_id": str(row.id), "stripe_invoice_id": stripe_invoice_id,
                    "local_status": old, "stripe_status": new_status}})
            return 0
        row.status = new_status
        if new_status == "paid" and not row.paid_at:
            row.paid_at = timezone.now()
            row.amount_paid_micros = (getattr(inv, "amount_paid", 0) or 0) * 10_000
        refresh_urls(row, inv)
        row.save()
    return 1 if new_status != old else 0
