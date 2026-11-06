import logging

from django.db import transaction
from django.utils import timezone

from apps.billing.connectors.stripe.invoice_routing import event_livemode, livemode_filter
from apps.billing.stripe.services.stripe_service import field
from apps.subscriptions.models import StripeSubscription
from apps.subscriptions.stripe.binding import (
    AMBIGUOUS, UNRESOLVED, AmbiguousMirrorOwner, create_bound_mirror, log_unbound,
    mutable_facts, resolve_new_mirror_owner, stripe_customer_id_of)
from apps.subscriptions.stripe.items import _period_end, _period_start, _product_name, mirrored_amounts
from apps.platform.customers.models import Customer

logger = logging.getLogger(__name__)


def handle_subscription_created(event):
    """New subscription on a tenant's connected account: bind its mirror once.

    THE EXISTING MIRROR IS LOOKED UP FIRST (R10 Stage C4, PLAN §7 item 37).
    When one exists, by Stripe subscription id, this delivery is a replay or
    arrived after the sync or UBB's own subscribe bound it. Its binding
    stands and nothing is re-resolved, so duplicate Stripe customer ids can
    never make it fail. Nothing is rewritten either: a ``created`` event
    carries the subscription as it was at creation, older than anything the
    mirror has since been told.

    A subscription with no mirror binds through the one shared resolver
    (``apps/subscriptions/stripe/binding.py``), in the event's namespace:
    its connected account, its livemode and the charged Stripe customer id.
    Exactly one holder binds the mirror to that customer and its tenant. No
    holder (``Customer.DoesNotExist``) or several (``AmbiguousMirrorOwner``)
    raises, so the receiver records a retryable failure and Stripe
    redelivers; no mirror is guessed.
    """
    stripe_sub = event.data.object
    sub_id = field(stripe_sub, "id")
    if StripeSubscription.objects.filter(stripe_subscription_id=sub_id).exists():
        return

    connected_account = event.account
    livemode = event_livemode(event)
    stripe_customer_id = stripe_customer_id_of(stripe_sub)
    resolution = resolve_new_mirror_owner(
        connected_account=connected_account, livemode=livemode,
        stripe_customer_id=stripe_customer_id)
    if resolution.outcome in (UNRESOLVED, AMBIGUOUS):
        log_unbound(resolution, stripe_subscription_id=sub_id,
                    stripe_customer_id=stripe_customer_id,
                    connected_account=connected_account, livemode=livemode,
                    via="webhook")
        if resolution.outcome == AMBIGUOUS:
            raise AmbiguousMirrorOwner(
                f"{len(resolution.holders)} customers hold Stripe customer "
                f"{stripe_customer_id} on {connected_account}; subscription "
                f"{sub_id} binds to none of them")
        raise Customer.DoesNotExist(
            f"no customer holds Stripe customer {stripe_customer_id} on "
            f"{connected_account}; subscription {sub_id} is not mirrored")
    create_bound_mirror(
        sub_id, customer_id=resolution.customer_id, tenant_id=resolution.tenant_id,
        facts=mutable_facts(stripe_sub))


def handle_subscription_updated(event):
    """Subscription changed -- update local mirror."""
    stripe_sub = event.data.object
    with transaction.atomic():
        sub = StripeSubscription.objects.select_for_update().get(
            stripe_subscription_id=stripe_sub.id,
            **livemode_filter(event),
        )
        money = mirrored_amounts(stripe_sub)
        sub.status = stripe_sub.status
        sub.stripe_product_name = _product_name(stripe_sub) or sub.stripe_product_name
        sub.amount_micros = money.amount_micros
        sub.currency = money.currency
        sub.source_amount_minor = money.source_amount_minor
        sub.interval = money.interval
        sub.current_period_start = _period_start(stripe_sub)
        sub.current_period_end = _period_end(stripe_sub)
        sub.last_synced_at = timezone.now()
        sub.quantity = money.seat_qty
        # F5.4 lifecycle flags: Stripe keeps status "active" both under a
        # pending cancel_at_period_end and under pause_collection, so the
        # mirror carries them explicitly (pause_collection presence => paused).
        # On the real object ``pause_collection`` is a StripeObject when
        # present (truthy even when empty) and None or absent when not (F-3b).
        sub.cancel_at_period_end = bool(field(stripe_sub, "cancel_at_period_end", False))
        sub.paused = field(stripe_sub, "pause_collection") is not None
        sub.save(update_fields=[
            "status", "stripe_product_name", "amount_micros", "currency",
            "source_amount_minor", "interval",
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
