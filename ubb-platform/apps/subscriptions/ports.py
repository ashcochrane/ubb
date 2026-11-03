"""Subscriptions' billing-facing ports.

The ONLY subscriptions module billing may import. Billing's Stripe connector
(the invoice.payment_failed webhook fast path and the hourly AR reconcile
poller) must stamp/repair subscription AR rows without reaching into
subscriptions internals, so the SubscriptionInvoice / StripeSubscription ORM
stays on this side of the boundary; billing passes plain data + the Stripe
invoice object. Reusing billing's invoice_routing helpers here is the
sanctioned Stripe connector-kit import (subscriptions -> billing), the same
exception orchestration/service.py relies on — it keeps the webhook fast path
and the poller on ONE Stripe-legal transition table so they can never diverge.
"""
import logging

from django.db import transaction
from django.utils import timezone

from apps.billing.connectors.stripe.invoice_routing import (
    SETTLED_PAYMENT_STATUSES, _refresh_urls, ar_transition_allowed, settle_failure_stamp)
from apps.subscriptions.stripe.items import paid_amounts

logger = logging.getLogger(__name__)


def get_active_subscription_for_consolidation(tenant, customer):
    """F5.5 consolidation eligibility: the customer's ACTIVE UBB-managed
    Stripe subscription, as plain data (ADR-001: billing may import only this
    module, never the subscriptions ORM).

    Eligible: mirror status "active" or "past_due" (a past_due renewal still
    drafts the next invoice), not paused (a paused subscription's draft may
    never auto-finalize — items pinned to it would never bill), and carrying
    at least one CustomerSubscriptionItem with a UBB plan attached (the
    UBB-managed marker; a foreign Stripe subscription is not ours to ride).

    Returns ``{"stripe_subscription_id": ...}`` or ``None``.
    """
    from apps.subscriptions.models import StripeSubscription

    sub = (
        StripeSubscription.objects.filter(
            tenant=tenant, customer=customer,
            status__in=["active", "past_due"], paused=False,
            line_items__plan__isnull=False,
        )
        .order_by("-created_at")
        .first()
    )
    if not sub:
        return None
    return {"stripe_subscription_id": sub.stripe_subscription_id}


def mark_invoice_payment_failed_for_subscription(account, subscription_id, stripe_invoice_id, inv,
                                                 *, livemode=True):
    """Stamp payment_failed_at + refresh hosted url on the SubscriptionInvoice
    matched by a subscription-linked invoice.payment_failed event, and say
    whose standing failure it is.

    Status-only (no money movement); account-checked via the owning
    StripeSubscription's tenant; idempotent; never touches the status column.
    ``livemode`` binds the event's mode to the tenant's mode (F4.4): a Connect
    acct_ id is identical in test and live, so a livemode=False event may only
    ever stamp a sandbox tenant's rows.

    Returns the id of the canonical BILLING OWNER the stamped invoice
    represents (plain data — the customer the row names, resolved through
    `resolve_billing_owner`) when the row is a STANDING failure: the customer
    billing's payment-failed suspension targets (R10 Stage C2, RULED Q4 a).
    None when no local row matched (Q4 c: nobody is suspended), and None for
    a row already paid or void — a late failure event on a settled invoice is
    stamped as before but suspends nobody.
    """
    from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice

    sub = StripeSubscription.objects.filter(
        stripe_subscription_id=subscription_id,
        tenant__stripe_connected_account_id=account,
        tenant__is_sandbox=not livemode,
    ).first()
    if not sub:
        return None
    with transaction.atomic():
        row = SubscriptionInvoice.objects.select_for_update(of=("self",)).select_related(
            "customer", "customer__parent").filter(
            stripe_invoice_id=stripe_invoice_id,
            tenant=sub.tenant,  # pin to the mode-matched tenant, never a sibling's row
        ).first()
        if not row:
            return None
        row.payment_failed_at = timezone.now()
        _refresh_urls(row, inv)
        row.save(update_fields=[
            "payment_failed_at", "hosted_invoice_url", "invoice_pdf", "updated_at",
        ])
        if row.status in SETTLED_PAYMENT_STATUSES:
            return None
        return row.customer.resolve_billing_owner().id


def has_unsettled_subscription_payment_failure(owner_id) -> bool:
    """Does a SubscriptionInvoice of this billing owner (its own, or a pooled
    seat's it funds) still carry `payment_failed_at` while neither paid nor
    void? The subscriptions half of billing's "no qualifying failed/unpaid
    local invoice remains" question (R10 Stage C2, F-6) — plain data."""
    from apps.platform.customers.models import billed_to
    from apps.subscriptions.models import SubscriptionInvoice

    return (SubscriptionInvoice.objects
            .filter(billed_to(owner_id), payment_failed_at__isnull=False)
            .exclude(status__in=SETTLED_PAYMENT_STATUSES)
            .exists())


def settle_subscription_invoice_payment_failure(tenant, stripe_invoice_id):
    """The hourly AR repair observing a SETTLED status — `paid`, or `void`
    (PLAN §7 item 26) — on a SubscriptionInvoice clears that row's failure
    stamp (R10 Stage C2, F-6), whether the status transition applied in this
    pass or a webhook applied it earlier and the stamp lingered. Returns the
    billing owner id whose `payment_failed` suspension billing should then
    ask to clear (plain data), or None when the row is not settled or carries
    no stamp (so a replayed pass clears nothing twice). Billing makes the
    clear; this port never touches a customer's standing."""
    from apps.subscriptions.models import SubscriptionInvoice

    existing = SubscriptionInvoice.objects.filter(
        tenant=tenant, stripe_invoice_id=stripe_invoice_id,
        status__in=SETTLED_PAYMENT_STATUSES, payment_failed_at__isnull=False,
    ).first()
    if not existing:
        return None
    with transaction.atomic():
        row = SubscriptionInvoice.objects.select_for_update(of=("self",)).select_related(
            "customer", "customer__parent").get(id=existing.id)
        owner_id = settle_failure_stamp(row, row.status)
        if owner_id is not None:
            row.save(update_fields=["payment_failed_at", "updated_at"])
    return owner_id


def repair_subscription_invoice(tenant, stripe_invoice_id, inv, new_status):
    """Repair a SubscriptionInvoice status along the Stripe-legal transition
    table (shared with the webhook fast path). Returns 1 if changed."""
    from apps.subscriptions.models import SubscriptionInvoice

    existing = SubscriptionInvoice.objects.filter(
        tenant=tenant, stripe_invoice_id=stripe_invoice_id,
    ).first()
    if not existing:
        return 0
    with transaction.atomic():
        row = SubscriptionInvoice.objects.select_for_update().get(id=existing.id)
        old = row.status
        if not ar_transition_allowed(old, new_status):
            if new_status != old:
                logger.error("ar.reconcile_unexpected_regression", extra={"data": {
                    "subscription_invoice_id": str(row.id), "stripe_invoice_id": stripe_invoice_id,
                    "local_status": old, "stripe_status": new_status}})
            else:
                # Equal-status no-op still refreshes the hosted URLs: the token
                # rotates on payment_failed, and if that webhook was missed the
                # hourly pass is the only repair for a lingering open invoice.
                _refresh_urls(row, inv)
                row.save()
            return 0
        row.status = new_status
        if new_status == "paid" and not row.paid_at:
            row.paid_at = timezone.now()
            # The same reading the webhook fast path makes (`paid_amounts`), so
            # the repair re-observing one Stripe invoice can never state it a
            # second way — a foreign one stays quarantined here too (#564).
            row.currency, row.source_amount_paid_minor, row.amount_paid_micros = (
                paid_amounts(inv))
        _refresh_urls(row, inv)
        row.save()
    return 1
