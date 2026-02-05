import logging
from datetime import datetime, timezone as dt_timezone

from django.db import transaction
from django.utils import timezone

from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
from apps.platform.customers.models import Customer

logger = logging.getLogger(__name__)


def _unix_to_datetime(ts):
    """Convert unix timestamp to timezone-aware datetime."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=dt_timezone.utc)


def handle_subscription_created(event):
    """New subscription on tenant's Connected Account -- create local mirror."""
    stripe_sub = event.data.object
    connected_account = event.account

    customer = Customer.objects.get(
        stripe_customer_id=stripe_sub.customer,
        tenant__stripe_connected_account_id=connected_account,
    )

    StripeSubscription.objects.get_or_create(
        stripe_subscription_id=stripe_sub.id,
        defaults={
            "tenant": customer.tenant,
            "customer": customer,
            "stripe_product_name": stripe_sub.plan.product.name,
            "status": stripe_sub.status,
            "amount_micros": stripe_sub.plan.amount * 10_000,  # cents to micros
            "currency": stripe_sub.plan.currency,
            "interval": stripe_sub.plan.interval,
            "current_period_start": _unix_to_datetime(stripe_sub.current_period_start),
            "current_period_end": _unix_to_datetime(stripe_sub.current_period_end),
            "last_synced_at": timezone.now(),
        },
    )


def handle_subscription_updated(event):
    """Subscription changed -- update local mirror."""
    stripe_sub = event.data.object
    with transaction.atomic():
        sub = StripeSubscription.objects.select_for_update().get(
            stripe_subscription_id=stripe_sub.id
        )
        sub.status = stripe_sub.status
        sub.current_period_start = _unix_to_datetime(stripe_sub.current_period_start)
        sub.current_period_end = _unix_to_datetime(stripe_sub.current_period_end)
        sub.last_synced_at = timezone.now()
        sub.save(update_fields=[
            "status", "current_period_start", "current_period_end",
            "last_synced_at", "updated_at",
        ])


def handle_subscription_deleted(event):
    """Subscription canceled -- mark as canceled."""
    stripe_sub = event.data.object
    with transaction.atomic():
        sub = StripeSubscription.objects.select_for_update().get(
            stripe_subscription_id=stripe_sub.id
        )
        sub.status = "canceled"
        sub.last_synced_at = timezone.now()
        sub.save(update_fields=["status", "last_synced_at", "updated_at"])


def handle_invoice_paid(event):
    """A subscription invoice was paid -- record the revenue."""
    invoice = event.data.object
    if not invoice.subscription:
        return  # Not a subscription invoice -- skip

    try:
        stripe_sub = StripeSubscription.objects.get(
            stripe_subscription_id=invoice.subscription
        )
    except StripeSubscription.DoesNotExist:
        logger.warning(
            "StripeSubscription not found for invoice",
            extra={"data": {
                "stripe_invoice_id": invoice.id,
                "stripe_subscription_id": invoice.subscription,
            }},
        )
        raise  # Re-raise so webhook framework retries

    with transaction.atomic():
        SubscriptionInvoice.objects.get_or_create(
            stripe_invoice_id=invoice.id,
            defaults={
                "tenant": stripe_sub.tenant,
                "customer": stripe_sub.customer,
                "stripe_subscription": stripe_sub,
                "amount_paid_micros": invoice.amount_paid * 10_000,  # cents to micros
                "currency": invoice.currency,
                "period_start": _unix_to_datetime(invoice.period_start),
                "period_end": _unix_to_datetime(invoice.period_end),
                "paid_at": _unix_to_datetime(invoice.status_transitions.paid_at),
            },
        )
