"""Seat-roster -> Stripe subscription quantity coherence.

A business's billed seat quantity must equal its live active-seat roster
(R10 Stage C4, A-2, RULED Q8: automatic convergence required). Two parts:

1. **The immediate push.** Every roster change — a seat created through
   ``POST /customers``, a seat soft-deleted, suspended (the ``off`` floor, the
   enforcing stop, the C2 causes) or reactivated — calls
   ``notify_seat_roster_changed`` once inside its own transaction, and this
   module's listener pushes the full live count (never a delta) through
   ``SubscriptionOrchestrator.set_seats`` ``on_commit``: a rolled-back change
   never moves the Stripe quantity. It is a no-op unless the business has an
   active subscription with a seat-axis item. It never raises after the
   commit: a Stripe or orchestration failure is logged
   (``seat.qty_push_failed``) and the caller's request still succeeds.
2. **The hourly reconciler.** A push that failed after the roster committed
   is not left for the next roster change to repair.
   ``reconcile_seat_quantity`` (driven hourly by
   ``apps.subscriptions.tasks.reconcile_subscription_seat_quantities``)
   recomputes the live count for every business with an active seat
   subscription and, where it differs from the mirrored seat item's
   quantity, pushes it with the deterministic change id
   ``reconcile-{stripe_subscription_item_id}-{count}``. Every pass that finds
   the same difference replays ONE Stripe idempotency key, so the correction
   is applied once however many passes it takes to land.

The outbox is not the vehicle: it dead-letters after five retries
(``apps/platform/events/tasks.py``), so it could not guarantee convergence.
The reconciler reads the live count every hour until Stripe agrees.
"""
import logging
import uuid

from django.db import transaction

logger = logging.getLogger("ubb.billing")

# Stripe subscription statuses for which a seat-quantity push is meaningful.
_ACTIVE_SUB_STATUSES = ("active", "trialing", "past_due", "unpaid")

#: What one push, or one business's reconcile, came to.
PUSHED = "pushed"
RAIL_CLOSED = "rail_closed"
FAILED = "failed"
IN_STEP = "in_step"
NO_SEAT_SUBSCRIPTION = "no_seat_subscription"


def seat_count(business):
    """Number of LIVE active seats under a business.

    ``Customer.objects`` already excludes soft-deleted rows, so a removed seat
    drops out automatically; ``status="active"`` drops suspended/closed seats.
    """
    from apps.platform.customers.models import Customer

    return Customer.objects.filter(
        parent=business, account_type="seat", status="active"
    ).count()


def _resolve_seat_subscription(business):
    """Return (plan, seat_item) if the business has an active sub + seat item, else (None, None)."""
    from apps.subscriptions.models import CustomerSubscriptionItem, StripeSubscription

    has_sub = StripeSubscription.objects.filter(
        customer=business, status__in=_ACTIVE_SUB_STATUSES
    ).exists()
    if not has_sub:
        return None, None
    seat_item = (
        CustomerSubscriptionItem.objects.filter(customer=business, axis="seat")
        .select_related("plan")
        .order_by("-created_at")
        .first()
    )
    if seat_item is None or seat_item.plan is None:
        return None, None
    return seat_item.plan, seat_item


def businesses_with_an_active_seat_subscription():
    """Every business holding an active subscription with a seat-axis item,
    in a stable order: the population the hourly reconciler converges."""
    from apps.platform.customers.models import Customer
    from apps.subscriptions.models import CustomerSubscriptionItem

    holders = CustomerSubscriptionItem.objects.filter(
        axis="seat", stripe_subscription__status__in=_ACTIVE_SUB_STATUSES,
        customer__account_type="business").values_list("customer_id", flat=True)
    return Customer.objects.filter(id__in=holders).order_by("id")


def _push(business, plan, count, *, change_event_id, failure_log):
    """``set_seats`` for one business, never raising.

    Answers ``PUSHED`` when Stripe took the count. Otherwise it logs
    ``failure_log`` with the business id and the reason, and answers
    ``RAIL_CLOSED`` or ``FAILED``. It runs after a commit (the listener) and
    in the hourly pass, where a raise would either answer a client 500 for a
    change that already committed or stop the pass for every other business.
    """
    from apps.platform.tenants.models import PaymentRailClosed
    from apps.subscriptions.orchestration.service import SubscriptionOrchestrator

    data = {"business_id": str(business.id), "seats": count,
            "change_event_id": change_event_id}
    try:
        SubscriptionOrchestrator.set_seats(
            business, plan, count, change_event_id=change_event_id)
        return PUSHED
    except PaymentRailClosed:
        # G27: the rail is closed, so the quantity is not pushed — a
        # deliberate refusal, logged and skipped. PaymentRailClosed is a
        # StripeFatalError, so it is caught first.
        logger.warning(failure_log, extra={"data": {**data, "reason": "rail_closed"}})
        return RAIL_CLOSED
    except Exception as exc:
        # The ruled three — StripeFatalError, StripeTransientError,
        # OrchestrationError — and anything else: none is the caller's to
        # answer for, because the roster change committed, and the hourly
        # reconciler converges the quantity whatever stopped this push.
        logger.exception(failure_log, extra={"data": {**data, "reason": type(exc).__name__}})
        return FAILED


def sync_seat_quantity_on_commit(business, *, change_event_id=None):
    """If ``business`` has an active subscription + seat item, push the live seat
    count to Stripe AFTER the current transaction commits.

    No-op (cheaply) when the business has no subscription or no seat-axis item.
    Safe to call from any roster mutation; must run inside a transaction so the
    push is bound to the same commit as the roster change. It never fails the
    roster change: the read it makes now runs in its own savepoint, and a
    failure there is logged and left to the hourly reconciler.
    """
    if business is None or business.account_type != "business":
        return
    business_id = business.id
    try:
        with transaction.atomic():
            plan, _seat_item = _resolve_seat_subscription(business)
    except Exception as exc:
        logger.exception("seat.qty_push_failed", extra={"data": {
            "business_id": str(business_id), "reason": type(exc).__name__}})
        return
    if plan is None:
        return
    if _a_push_is_queued_for(business_id):
        # One transaction, several roster changes: the push already queued
        # recounts the roster when the transaction commits, so it carries the
        # final count. A second push would only repeat it.
        return

    event_id = change_event_id or str(uuid.uuid4())

    def _push_after_commit():
        from apps.platform.customers.models import Customer

        biz = Customer.objects.filter(id=business_id).first()
        if biz is None:
            return
        # Re-resolve at commit time: roster + subscription state may have moved.
        live_plan, _ = _resolve_seat_subscription(biz)
        if live_plan is None:
            return
        _push(biz, live_plan, seat_count(biz), change_event_id=event_id,
              failure_log="seat.qty_push_failed")

    _push_after_commit.seat_roster_business_id = business_id
    transaction.on_commit(_push_after_commit)


def _a_push_is_queued_for(business_id):
    """Is a push for ``business_id`` already waiting on the current
    transaction's commit? Read from the connection's own pending on-commit
    callbacks, ``(savepoint ids, callable, robust)`` entries (Django 6.0's
    shape, held by the rollback test beside the one-push test), which Django
    drops when the savepoint that queued them rolls back, so a rolled-back
    change never leaves a push suppressed. Outside a transaction a callback
    runs at once and nothing is pending."""
    connection = transaction.get_connection()
    return any(getattr(func, "seat_roster_business_id", None) == business_id
               for _sids, func, _robust in connection.run_on_commit)


def reconcile_seat_quantity(business):
    """Converge one business's billed seat quantity on its live roster.

    Compares the live count with the quantity the mirrored seat item last
    recorded Stripe as holding, and pushes only when they differ, under the
    deterministic change id ``reconcile-{stripe_subscription_item_id}-{count}``:
    a pass that finds the same difference again replays the same Stripe
    idempotency key, and a pass that finds none makes no call. A closed rail
    is logged and skipped, as the listener does. Answers ``IN_STEP``,
    ``NO_SEAT_SUBSCRIPTION`` or what ``_push`` answered.
    """
    plan, seat_item = _resolve_seat_subscription(business)
    if plan is None:
        return NO_SEAT_SUBSCRIPTION
    count = seat_count(business)
    if seat_item.quantity == count:
        return IN_STEP
    return _push(
        business, plan, count,
        change_event_id=f"reconcile-{seat_item.stripe_subscription_item_id}-{count}",
        failure_log="seat.qty_reconcile_failed")
