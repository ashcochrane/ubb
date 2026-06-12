import logging

from django.db import transaction
from django.utils import timezone

from apps.billing.connectors.stripe.invoice_routing import livemode_filter
from apps.subscriptions.models import StripeSubscription
from apps.subscriptions.stripe.items import _sum_items, _period_start, _period_end, _product_name
from apps.platform.customers.models import Customer

logger = logging.getLogger(__name__)


def handle_subscription_created(event):
    """New subscription on tenant's Connected Account -- create local mirror."""
    stripe_sub = event.data.object
    connected_account = event.account

    try:
        customer = Customer.objects.get(
            stripe_customer_id=stripe_sub.customer,
            tenant__stripe_connected_account_id=connected_account,
            **livemode_filter(event),
        )
    except Customer.DoesNotExist:
        logger.warning(
            "Subscription created for unknown customer",
            extra={"data": {
                "stripe_customer_id": stripe_sub.customer,
                "connected_account": connected_account,
            }},
        )
        raise  # Re-raise so webhook framework retries

    amount_micros, seat_qty, interval = _sum_items(stripe_sub)
    StripeSubscription.objects.get_or_create(
        stripe_subscription_id=stripe_sub.id,
        defaults={
            "tenant": customer.tenant,
            "customer": customer,
            "stripe_product_name": _product_name(stripe_sub),
            "status": stripe_sub.status,
            "amount_micros": amount_micros,
            "currency": stripe_sub.get("currency", "usd"),
            "interval": interval,
            "current_period_start": _period_start(stripe_sub),
            "current_period_end": _period_end(stripe_sub),
            "last_synced_at": timezone.now(),
            "quantity": seat_qty,
        },
    )


def handle_subscription_updated(event):
    """Subscription changed -- update local mirror."""
    stripe_sub = event.data.object
    with transaction.atomic():
        sub = StripeSubscription.objects.select_for_update().get(
            stripe_subscription_id=stripe_sub.id,
            **livemode_filter(event),
        )
        amount_micros, seat_qty, interval = _sum_items(stripe_sub)
        sub.status = stripe_sub.status
        sub.stripe_product_name = _product_name(stripe_sub) or sub.stripe_product_name
        sub.amount_micros = amount_micros
        sub.interval = interval
        sub.current_period_start = _period_start(stripe_sub)
        sub.current_period_end = _period_end(stripe_sub)
        sub.last_synced_at = timezone.now()
        sub.quantity = seat_qty
        # F5.4 lifecycle flags: Stripe keeps status "active" both under a
        # pending cancel_at_period_end and under pause_collection, so the
        # mirror carries them explicitly (pause_collection presence => paused).
        sub.cancel_at_period_end = bool(stripe_sub.get("cancel_at_period_end") or False)
        sub.paused = bool(stripe_sub.get("pause_collection") or False)
        sub.save(update_fields=[
            "status", "stripe_product_name", "amount_micros", "interval",
            "current_period_start", "current_period_end",
            "last_synced_at", "updated_at", "quantity",
            "cancel_at_period_end", "paused",
        ])


def handle_subscription_deleted(event):
    """Subscription canceled -- mark as canceled.

    Idempotent against a mirror already pre-updated by the orchestrator's
    immediate cancel (F5.4): re-asserting status="canceled" is harmless and an
    existing canceled_at is preserved (the orchestrator's timestamp wins).
    """
    stripe_sub = event.data.object
    with transaction.atomic():
        sub = StripeSubscription.objects.select_for_update().get(
            stripe_subscription_id=stripe_sub.id,
            **livemode_filter(event),
        )
        sub.status = "canceled"
        if sub.canceled_at is None:
            sub.canceled_at = timezone.now()
        sub.last_synced_at = timezone.now()
        sub.save(update_fields=["status", "canceled_at", "last_synced_at", "updated_at"])


# NOTE: invoice.paid is intentionally NOT handled here. ALL invoice.* reconcile
# (including SubscriptionInvoice payment status + revenue capture) lives on api/v1
# — see api/v1/webhooks.py::_reconcile_customer_invoice. Both endpoints share the
# StripeWebhookEvent dedup table, so handling an invoice.* event on both would let
# the first win the dedup row and the second silently skip (C-1).
