import logging
from datetime import datetime, timezone as dt_timezone

import stripe
from django.utils import timezone

from apps.subscriptions.models import StripeSubscription
from apps.platform.customers.models import Customer

logger = logging.getLogger(__name__)


def _unix_to_datetime(ts):
    """Convert unix timestamp to timezone-aware datetime."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=dt_timezone.utc)


def sync_subscriptions(tenant):
    """Full sync of active subscriptions from tenant's Connected Account.

    Returns dict with counts: {"synced": N, "skipped": N, "errors": N}
    """
    if not tenant.stripe_connected_account_id:
        logger.warning("Tenant has no stripe_connected_account_id", extra={
            "data": {"tenant_id": str(tenant.id)},
        })
        return {"synced": 0, "skipped": 0, "errors": 0}

    # Build a lookup of stripe_customer_id -> Customer for this tenant
    customers_by_stripe_id = {
        c.stripe_customer_id: c
        for c in Customer.objects.filter(
            tenant=tenant,
            stripe_customer_id__gt="",
        )
    }

    try:
        subscriptions = stripe.Subscription.list(
            status="all",
            stripe_account=tenant.stripe_connected_account_id,
            expand=["data.plan.product"],
        )
    except stripe.error.StripeError:
        logger.exception("Stripe API error during subscription sync", extra={
            "data": {"tenant_id": str(tenant.id)},
        })
        return {"synced": 0, "skipped": 0, "errors": 1}

    synced = 0
    skipped = 0
    errors = 0

    for stripe_sub in subscriptions.auto_paging_iter():
        customer = customers_by_stripe_id.get(stripe_sub.customer)
        if not customer:
            logger.info("Skipping subscription — no matching customer", extra={
                "data": {
                    "stripe_subscription_id": stripe_sub.id,
                    "stripe_customer_id": stripe_sub.customer,
                },
            })
            skipped += 1
            continue

        try:
            StripeSubscription.objects.update_or_create(
                stripe_subscription_id=stripe_sub.id,
                defaults={
                    "tenant": tenant,
                    "customer": customer,
                    "stripe_product_name": stripe_sub.plan.product.name,
                    "status": stripe_sub.status,
                    "amount_micros": stripe_sub.plan.amount * 10_000,
                    "currency": stripe_sub.plan.currency,
                    "interval": stripe_sub.plan.interval,
                    "current_period_start": _unix_to_datetime(stripe_sub.current_period_start),
                    "current_period_end": _unix_to_datetime(stripe_sub.current_period_end),
                    "last_synced_at": timezone.now(),
                },
            )
            synced += 1
        except Exception:
            logger.exception("Error syncing subscription", extra={
                "data": {"stripe_subscription_id": stripe_sub.id},
            })
            errors += 1

    return {"synced": synced, "skipped": skipped, "errors": errors}
