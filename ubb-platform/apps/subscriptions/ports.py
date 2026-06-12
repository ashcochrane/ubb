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

from apps.billing.connectors.stripe.invoice_routing import _refresh_urls, ar_transition_allowed

logger = logging.getLogger(__name__)


def mark_invoice_payment_failed_for_subscription(account, subscription_id, stripe_invoice_id, inv,
                                                 *, livemode=True):
    """Stamp payment_failed_at + refresh hosted url on the SubscriptionInvoice
    matched by a subscription-linked invoice.payment_failed event.

    Status-only (no money movement); account-checked via the owning
    StripeSubscription's tenant; idempotent; never touches the status column.
    ``livemode`` binds the event's mode to the tenant's mode (F4.4): a Connect
    acct_ id is identical in test and live, so a livemode=False event may only
    ever stamp a sandbox tenant's rows. Returns True if a row was stamped.
    """
    from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice

    sub = StripeSubscription.objects.filter(
        stripe_subscription_id=subscription_id,
        tenant__stripe_connected_account_id=account,
        tenant__is_sandbox=not livemode,
    ).first()
    if not sub:
        return False
    with transaction.atomic():
        row = SubscriptionInvoice.objects.select_for_update().filter(
            stripe_invoice_id=stripe_invoice_id,
        ).first()
        if not row:
            return False
        row.payment_failed_at = timezone.now()
        _refresh_urls(row, inv)
        row.save(update_fields=[
            "payment_failed_at", "hosted_invoice_url", "invoice_pdf", "updated_at",
        ])
    return True


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
            row.amount_paid_micros = (getattr(inv, "amount_paid", 0) or 0) * 10_000
        _refresh_urls(row, inv)
        row.save()
    return 1
