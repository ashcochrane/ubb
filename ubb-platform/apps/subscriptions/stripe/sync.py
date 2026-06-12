import logging
from datetime import datetime, timezone as dt_timezone

import stripe
from django.utils import timezone

from apps.billing.stripe.services.stripe_service import api_key_for_tenant
from apps.subscriptions.models import StripeSubscription
from apps.subscriptions.stripe.items import _sum_items, _period_start, _period_end, _product_name
from apps.platform.queries import get_tenant_stripe_account, get_customers_by_stripe_id
from core.exceptions import StripeFatalError

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
    connected_account = get_tenant_stripe_account(tenant.id)
    if not connected_account:
        logger.warning("Tenant has no stripe_connected_account_id", extra={
            "data": {"tenant_id": str(tenant.id)},
        })
        return {"synced": 0, "skipped": 0, "errors": 0}

    # Build a lookup of stripe_customer_id -> customer_id for this tenant
    customers_by_stripe_id = get_customers_by_stripe_id(tenant.id)

    try:
        subscriptions = stripe.Subscription.list(
            status="all",
            stripe_account=connected_account,
            expand=["data.items.data.price.product"],
            api_key=api_key_for_tenant(tenant),
        )
    except StripeFatalError:
        # F4.4: sandbox tenant without STRIPE_TEST_SECRET_KEY configured.
        logger.warning("Stripe key unavailable for tenant mode — sync skipped", extra={
            "data": {"tenant_id": str(tenant.id)},
        })
        return {"synced": 0, "skipped": 0, "errors": 1}
    except stripe.error.StripeError:
        logger.exception("Stripe API error during subscription sync", extra={
            "data": {"tenant_id": str(tenant.id)},
        })
        return {"synced": 0, "skipped": 0, "errors": 1}

    synced = 0
    skipped = 0
    errors = 0

    for stripe_sub in subscriptions.auto_paging_iter():
        customer_id = customers_by_stripe_id.get(stripe_sub.customer)
        if not customer_id:
            logger.info("Skipping subscription — no matching customer", extra={
                "data": {
                    "stripe_subscription_id": stripe_sub.id,
                    "stripe_customer_id": stripe_sub.customer,
                },
            })
            skipped += 1
            continue

        try:
            amount_micros, seat_qty, interval = _sum_items(stripe_sub)
            StripeSubscription.objects.update_or_create(
                stripe_subscription_id=stripe_sub.id,
                defaults={
                    "tenant": tenant,
                    "customer_id": customer_id,
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
            synced += 1
        except Exception:
            logger.exception("Error syncing subscription", extra={
                "data": {"stripe_subscription_id": stripe_sub.id},
            })
            errors += 1

    return {"synced": synced, "skipped": skipped, "errors": errors}
