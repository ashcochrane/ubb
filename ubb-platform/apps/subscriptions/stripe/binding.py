"""Subscription-mirror identity: bind once, never rebind (R10 Stage C4, PLAN
§7 items 30 and 33-38, "Option 1").

A mirror's ``customer`` and ``tenant`` are its BINDING, the durable fact of
whose subscription it is. The C2 invoice path freezes a new subscription
invoice's ``billing_owner`` from it (``api/v1/webhooks.py``), so a binding
that moved would freeze a wrong owner for good. Three rules hold it:

1. **An existing mirror is never rebound.** ``stripe_subscription_id``
   identifies it. The hourly and on-demand sync, a webhook replay and every
   other reconciliation write only the MUTABLE Stripe facts
   (``MUTABLE_FACT_FIELDS``), never ``customer`` or ``tenant``.
2. **A subscription UBB opened binds the owner UBB opened it for.**
   ``SubscriptionOrchestrator._persist_mirror`` holds that owner explicitly,
   creates the mirror with it, or confirms an existing binding equals it and
   refuses (``OrchestrationError``) when it does not.
3. **A subscription UBB discovers binds only to its one holder.** A
   subscription found on Stripe with no mirror resolves through
   ``resolve_new_mirror_owner``, the ONE resolver the webhook and the sync
   share, in the namespace connected account + livemode + Stripe customer id.
   Exactly one holder binds. None is UNRESOLVED and several are AMBIGUOUS;
   neither binds. There is no first, last or query-order winner: the
   resolver counts every holder (``apps.platform.queries.
   get_stripe_customer_holders``) and only a count of one answers.

There is no automatic rebind. A mirror bound once stays bound when customers
that share or edit Stripe ids change later. Rebinding, if UBB ever needs it,
is a separately designed operator workflow with stated economic consequences.
The ambiguity is logged as the ERROR ``subscription.mirror_ambiguous`` and the
unresolved case as ``subscription.mirror_unresolved``: operational
diagnostics, not public events or vocabulary.
"""
import logging
from dataclasses import dataclass

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.billing.stripe.services.stripe_service import field
from apps.platform.queries import get_stripe_customer_holders
from apps.subscriptions.models import StripeSubscription
from apps.subscriptions.stripe.items import (
    _period_end, _period_start, _product_name, mirrored_amounts)

logger = logging.getLogger(__name__)

#: What a resolution answers.
BOUND = "bound"
UNRESOLVED = "unresolved"
AMBIGUOUS = "ambiguous"

#: The columns a sync or a replay may write on an EXISTING mirror: Stripe's
#: own mutable facts. ``customer`` and ``tenant`` are absent by design.
MUTABLE_FACT_FIELDS = (
    "stripe_product_name", "status", "amount_micros", "currency",
    "source_amount_minor", "interval", "current_period_start",
    "current_period_end", "last_synced_at", "quantity",
)


class AmbiguousMirrorOwner(ObjectDoesNotExist):
    """No ONE customer holds the subscription's Stripe customer id in its
    namespace: several do. Nothing is bound. It is an ``ObjectDoesNotExist``
    because no unique owner exists, so the webhook receiver records it as a
    retryable failure (500) exactly as it records an out-of-order event, and
    Stripe redelivers until the ambiguity is removed or a binding exists."""


@dataclass(frozen=True)
class Resolution:
    """The answer for one new mirror: ``outcome`` is BOUND, UNRESOLVED or
    AMBIGUOUS. ``customer_id`` and ``tenant_id`` are set for BOUND only;
    ``holders`` lists every holder found, for the log."""
    outcome: str
    customer_id: str | None = None
    tenant_id: str | None = None
    holders: tuple = ()


def stripe_customer_id_of(stripe_sub):
    """The Stripe customer id a subscription charges: an id string, or the id
    of an expanded Customer object."""
    customer = field(stripe_sub, "customer")
    return customer if isinstance(customer, str) else field(customer, "id")


def resolve_new_mirror_owner(*, connected_account, livemode, stripe_customer_id):
    """THE resolver for a subscription that has no mirror yet.

    Counts every live customer that holds ``stripe_customer_id`` in a tenant
    holding ``connected_account`` in the matching mode, and binds only when
    the count is exactly one. Never consulted for a subscription that already
    has a mirror: that one is bound already.
    """
    holders = tuple(get_stripe_customer_holders(
        connected_account, livemode=livemode, stripe_customer_id=stripe_customer_id))
    if len(holders) == 1:
        (holder,) = holders
        return Resolution(BOUND, holder["customer_id"], holder["tenant_id"], holders)
    return Resolution(AMBIGUOUS if holders else UNRESOLVED, holders=holders)


def log_unbound(resolution, *, stripe_subscription_id, stripe_customer_id,
                connected_account, livemode, via, unresolved_level=logging.WARNING):
    """The structured line for a new mirror that did not bind. An ambiguity
    is always an ERROR, ``subscription.mirror_ambiguous``, naming every
    holder; an unresolved one is ``subscription.mirror_unresolved``."""
    data = {
        "stripe_subscription_id": stripe_subscription_id,
        "stripe_customer_id": stripe_customer_id,
        "connected_account": connected_account,
        "livemode": livemode,
        "via": via,
        "holder_count": len(resolution.holders),
    }
    if resolution.outcome == AMBIGUOUS:
        data["holders"] = [dict(h) for h in resolution.holders]
        logger.error("subscription.mirror_ambiguous", extra={"data": data})
    else:
        logger.log(unresolved_level, "subscription.mirror_unresolved",
                   extra={"data": data})


def mutable_facts(stripe_sub):
    """The mutable Stripe facts of a subscription, keyed by mirror column."""
    money = mirrored_amounts(stripe_sub)
    return {
        "stripe_product_name": _product_name(stripe_sub),
        "status": field(stripe_sub, "status"),
        "amount_micros": money.amount_micros,
        "currency": money.currency,
        "source_amount_minor": money.source_amount_minor,
        "interval": money.interval,
        "current_period_start": _period_start(stripe_sub),
        "current_period_end": _period_end(stripe_sub),
        "last_synced_at": timezone.now(),
        "quantity": money.seat_qty,
    }


def refresh_mutable_facts(mirror, stripe_sub):
    """Write a subscription's mutable facts onto its EXISTING mirror. Only
    ``MUTABLE_FACT_FIELDS`` are saved, so the binding cannot move here."""
    for name, value in mutable_facts(stripe_sub).items():
        setattr(mirror, name, value)
    mirror.save(update_fields=[*MUTABLE_FACT_FIELDS, "updated_at"])
    return mirror


def create_bound_mirror(stripe_sub, *, customer_id, tenant_id):
    """Create a NEW mirror bound to ``customer_id`` / ``tenant_id``.

    Returns ``(mirror, True)`` when this call created it. A writer that bound
    the same subscription first wins: the unique ``stripe_subscription_id``
    refuses the second row, and this returns that existing mirror, untouched,
    as ``(mirror, False)``. Its binding stands either way.
    """
    sub_id = field(stripe_sub, "id")
    try:
        with transaction.atomic():
            return StripeSubscription.objects.create(
                stripe_subscription_id=sub_id, customer_id=customer_id,
                tenant_id=tenant_id, **mutable_facts(stripe_sub)), True
    except IntegrityError:
        existing = StripeSubscription.objects.filter(stripe_subscription_id=sub_id).first()
        if existing is None:
            raise  # another constraint refused the row: not a race
        return existing, False
