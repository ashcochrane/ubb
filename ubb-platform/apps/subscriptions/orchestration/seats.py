"""Seat-roster -> Stripe subscription quantity coherence.

A business's billed seat quantity must equal its live active-seat roster. Any
roster change (seat create / remove / suspend / close) recomputes the count and
pushes it to Stripe via ``SubscriptionOrchestrator.set_seats`` -- but ONLY when
the business has an active subscription with a seat-axis item. Otherwise no-op.

The push is dispatched ``on_commit`` so it rides the SAME transaction as the
roster change: a rolled-back roster change never moves the Stripe quantity, and
a committed one always does. Failures here must never break the roster write, so
the callback swallows + logs orchestration errors (the hourly subscription sync /
reconciler is the backstop).
"""
import logging
import uuid

from django.db import transaction

logger = logging.getLogger("ubb.billing")

# Stripe subscription statuses for which a seat-quantity push is meaningful.
_ACTIVE_SUB_STATUSES = ("active", "trialing", "past_due", "unpaid")


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


def sync_seat_quantity_on_commit(business, *, change_event_id=None):
    """If ``business`` has an active subscription + seat item, push the live seat
    count to Stripe AFTER the current transaction commits.

    No-op (cheaply) when the business has no subscription or no seat-axis item.
    Safe to call from any roster mutation; must run inside a transaction so the
    push is bound to the same commit as the roster change.
    """
    if business is None or business.account_type != "business":
        return
    plan, _seat_item = _resolve_seat_subscription(business)
    if plan is None:
        return

    event_id = change_event_id or str(uuid.uuid4())
    business_id = business.id

    def _push():
        from apps.platform.customers.models import Customer
        from apps.subscriptions.orchestration.service import (
            OrchestrationError,
            SubscriptionOrchestrator,
        )

        biz = Customer.objects.filter(id=business_id).first()
        if biz is None:
            return
        # Re-resolve at commit time: roster + subscription state may have moved.
        live_plan, _ = _resolve_seat_subscription(biz)
        if live_plan is None:
            return
        try:
            SubscriptionOrchestrator.set_seats(
                biz, live_plan, seat_count(biz), change_event_id=event_id
            )
        except OrchestrationError:
            logger.exception(
                "seat.qty_push_failed", extra={"data": {"business_id": str(business_id)}}
            )

    transaction.on_commit(_push)
