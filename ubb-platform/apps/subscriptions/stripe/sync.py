import logging
from datetime import datetime, timezone as dt_timezone

import stripe

from apps.billing.stripe.services.stripe_service import api_key_for_tenant, field, stripe_call
from apps.subscriptions.models import StripeSubscription
from apps.subscriptions.stripe.binding import (
    BOUND, create_bound_mirror, log_unbound, mutable_facts, refresh_mutable_facts,
    resolve_new_mirror_owner, stripe_customer_id_of)
from apps.platform.queries import get_tenant_stripe_account
from core.exceptions import StripeFatalError, StripeTransientError

logger = logging.getLogger(__name__)


def _unix_to_datetime(ts):
    """Convert unix timestamp to timezone-aware datetime."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=dt_timezone.utc)


def sync_subscriptions(tenant):
    """Full sync of the subscriptions on a tenant's connected account.

    Returns dict with counts: {"synced": N, "skipped": N, "errors": N}

    BIND ONCE, NEVER REBIND (R10 Stage C4, PLAN §7 items 33-35;
    ``apps/subscriptions/stripe/binding.py``). For each listed subscription:

    - **It has a mirror of this tenant's:** its mutable Stripe facts are
      refreshed and its binding is not touched (``synced``).
    - **It has a mirror of another tenant's** (two tenants may hold one
      connected account): nothing of that tenant is written (``skipped``).
    - **It has no mirror:** the one shared resolver answers. Exactly one
      holder, in THIS tenant, binds it (``synced``). No holder, several
      holders, or one holder in another tenant binds nothing here
      (``skipped``); that tenant's own sync or the account-scoped webhook
      binds it.

    The response shape is unchanged.
    """
    connected_account = get_tenant_stripe_account(tenant.id)
    if not connected_account:
        logger.warning("Tenant has no stripe_connected_account_id", extra={
            "data": {"tenant_id": str(tenant.id)},
        })
        return {"synced": 0, "skipped": 0, "errors": 0}

    # Through the wrapper (F-2): no key for the tenant's mode is refused before
    # transport. Every page is fetched INSIDE the try — auto_paging_iter()
    # requests the next page lazily, and a failure there must land here.
    try:
        subscriptions = stripe_call(
            stripe.Subscription.list,
            api_key=api_key_for_tenant(tenant),
            status="all",
            stripe_account=connected_account,
            expand=["data.items.data.price.product"],
        )
        listed = list(subscriptions.auto_paging_iter())
    except StripeFatalError:
        # F4.4: no key for the tenant's mode (sandbox without
        # STRIPE_TEST_SECRET_KEY, an unset live key), or a non-retryable
        # Stripe refusal — nothing to sync.
        logger.warning("Stripe key unavailable or call refused for tenant mode — sync skipped",
                       extra={"data": {"tenant_id": str(tenant.id)}})
        return {"synced": 0, "skipped": 0, "errors": 1}
    except (StripeTransientError, stripe.error.StripeError):
        logger.exception("Stripe API error during subscription sync", extra={
            "data": {"tenant_id": str(tenant.id)},
        })
        return {"synced": 0, "skipped": 0, "errors": 1}

    livemode = not tenant.is_sandbox
    synced = 0
    skipped = 0
    errors = 0

    for stripe_sub in listed:
        try:
            if _sync_one(tenant, connected_account, livemode, stripe_sub):
                synced += 1
            else:
                skipped += 1
        except Exception:
            logger.exception("Error syncing subscription", extra={
                "data": {"stripe_subscription_id": field(stripe_sub, "id")},
            })
            errors += 1

    return {"synced": synced, "skipped": skipped, "errors": errors}


def _sync_one(tenant, connected_account, livemode, stripe_sub):
    """Mirror one listed subscription for ``tenant``. True when this tenant's
    mirror was written (refreshed or newly bound), False when skipped."""
    sub_id = field(stripe_sub, "id")
    existing = StripeSubscription.objects.filter(stripe_subscription_id=sub_id).first()
    if existing is not None:
        if existing.tenant_id != tenant.id:
            logger.info("subscription.mirror_of_another_tenant", extra={"data": {
                "stripe_subscription_id": sub_id, "tenant_id": str(tenant.id),
                "bound_tenant_id": str(existing.tenant_id)}})
            return False
        refresh_mutable_facts(existing, stripe_sub)
        return True

    stripe_customer_id = stripe_customer_id_of(stripe_sub)
    resolution = resolve_new_mirror_owner(
        connected_account=connected_account, livemode=livemode,
        stripe_customer_id=stripe_customer_id)
    if resolution.outcome != BOUND:
        # A subscription for a Stripe customer UBB does not know is ordinary
        # on a connected account, so an unresolved one is INFO here; an
        # ambiguous one is always the ERROR.
        log_unbound(resolution, stripe_subscription_id=sub_id,
                    stripe_customer_id=stripe_customer_id,
                    connected_account=connected_account, livemode=livemode,
                    via="sync", unresolved_level=logging.INFO)
        return False
    if resolution.tenant_id != str(tenant.id):
        logger.info("subscription.mirror_left_to_its_tenant", extra={"data": {
            "stripe_subscription_id": sub_id, "tenant_id": str(tenant.id),
            "holder_tenant_id": resolution.tenant_id}})
        return False
    mirror, created = create_bound_mirror(
        sub_id, customer_id=resolution.customer_id, tenant_id=resolution.tenant_id,
        facts=mutable_facts(stripe_sub))
    if not created:
        # Bound by a concurrent writer between the read above and the
        # create: its binding stands, and only a mirror of this tenant's is
        # refreshed.
        if mirror.tenant_id != tenant.id:
            return False
        refresh_mutable_facts(mirror, stripe_sub)
    return True
