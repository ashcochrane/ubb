# Billing-owned invoice routing helpers.
#
# Moved here from api/v1/webhooks.py to break the circular import:
# api/v1/webhooks.py eagerly imports handlers FROM
# apps/billing/connectors/stripe/webhooks.py, which means
# apps/billing can never safely import api/v1. Placing these
# helpers here (billing-domain logic they always were) lets both
# the webhook handler module and the invoicing task module import
# them directly, with zero circularity.
#
# The four payment statuses are the registry's closed
# `usage_invoice_payment_status` (R10 Stage C5, F-15), held here by reference
# — this module is the concept's backend consumer, because the AR transition
# table below is the facts the column records.
from core.vocabulary import (
    USAGE_INVOICE_PAYMENT_STATUS_OPEN,
    USAGE_INVOICE_PAYMENT_STATUS_PAID,
    USAGE_INVOICE_PAYMENT_STATUS_UNCOLLECTIBLE,
    USAGE_INVOICE_PAYMENT_STATUS_VALUES,
    USAGE_INVOICE_PAYMENT_STATUS_VOID,
)

# --- livemode <-> sandbox anti-collision (F4.4) -----------------------------
# A Stripe Connect acct_ id is IDENTICAL in test and live mode, so an
# event.account match alone cannot distinguish a live tenant from its sandbox
# sibling once both have completed (live/test) OAuth to the same account.
# Every event.account-based tenant/subscription/invoice lookup must therefore
# also bind the event's livemode to the tenant's mode: livemode=True events
# may only ever touch live tenants (is_sandbox=False), livemode=False events
# only sandbox tenants. These helpers are part of the Stripe connector kit
# (ADR-001 decision 5) so the subscriptions webhook handlers may import them.


def event_livemode(event):
    """The event's livemode flag, defaulting to LIVE when absent.

    Stripe always sends livemode; the default only matters for synthetic
    events in tests, which model live-mode traffic.
    """
    return bool(getattr(event, "livemode", True))


def livemode_filter(event, tenant_path="tenant"):
    """Filter kwargs binding a Stripe event's livemode to the tenant mode.

    Usage: ``Model.objects.filter(..., **livemode_filter(event))`` or, for a
    direct Tenant queryset, ``**livemode_filter(event, tenant_path="")``.
    """
    field = f"{tenant_path}__is_sandbox" if tenant_path else "is_sandbox"
    return {field: not event_livemode(event)}


def reject_for_mode(event, *, is_test_endpoint):
    """The livemode <-> endpoint gate (F4.4). Returns True if the event must 400.

    A test endpoint (verified with STRIPE_TEST_WEBHOOK_SECRET) accepts ONLY
    livemode=False events. A live endpoint rejects livemode=False ONLY when
    the test secret is configured — all-test dev setups (a single sk_test_
    key on the live endpoint, no sandbox infra) keep working unchanged.
    """
    from django.conf import settings

    livemode = event_livemode(event)
    if is_test_endpoint:
        return livemode
    return (not livemode) and bool(settings.STRIPE_TEST_WEBHOOK_SECRET)


# Stripe's documented invoice-status graph: uncollectible invoices remain
# payable and voidable; paid and void are genuinely final. The four statuses
# are the registry's closed `usage_invoice_payment_status` (R10 Stage C5,
# F-15), imported at the top of this module. The empty key is the NULL row
# state: no status yet (not yet collectible), which is null on the contract
# and no fifth value.
AR_ALLOWED = {
    "": set(USAGE_INVOICE_PAYMENT_STATUS_VALUES),   # None/'' = no status yet
    USAGE_INVOICE_PAYMENT_STATUS_OPEN: {
        USAGE_INVOICE_PAYMENT_STATUS_PAID, USAGE_INVOICE_PAYMENT_STATUS_VOID,
        USAGE_INVOICE_PAYMENT_STATUS_UNCOLLECTIBLE},
    USAGE_INVOICE_PAYMENT_STATUS_UNCOLLECTIBLE: {
        USAGE_INVOICE_PAYMENT_STATUS_PAID, USAGE_INVOICE_PAYMENT_STATUS_VOID},
    USAGE_INVOICE_PAYMENT_STATUS_PAID: set(),
    USAGE_INVOICE_PAYMENT_STATUS_VOID: set(),
}


def ar_transition_allowed(old, new):
    return new in AR_ALLOWED.get(old or "", set())


def _refresh_urls(local, inv):
    """Re-store hosted_invoice_url / invoice_pdf when present (Stripe rotates tokens)."""
    if getattr(inv, "hosted_invoice_url", None):
        local.hosted_invoice_url = inv.hosted_invoice_url
    if getattr(inv, "invoice_pdf", None):
        local.invoice_pdf = inv.invoice_pdf


def _invoice_subscription_id(inv):
    """Extract the subscription id from an invoice (legacy .subscription or Basil .parent)."""
    sub = getattr(inv, "subscription", None)
    if sub:
        return sub if isinstance(sub, str) else getattr(sub, "id", None)
    parent = getattr(inv, "parent", None)
    details = getattr(parent, "subscription_details", None) if parent else None
    s = getattr(details, "subscription", None) if details else None
    return s if isinstance(s, str) else getattr(s, "id", None)


# --- the failure stamp on a local invoice row (R10 Stage C2, F-6) ----------
#
# AR row state only, beside the transition table above: WHICH statuses settle
# a stamped invoice, and the one way a settled row's stamp is cleared. Whether
# the owner then comes back is billing's decision, made at its one
# reactivation site (`LiveCounter._maybe_unsuspend`) under the owner's row
# lock — never here, because this module is shared Stripe plumbing and not
# billing business logic (ADR-001 decision 5).

#: The payment statuses under which a stamped invoice no longer stands as a
#: payment failure: paid (resolved by payment) and void (RULED 2026-11-03, PLAN
#: §7 item 26: a resolved AR condition — NOT economically paid, but no longer
#: an outstanding failure that can keep the owner suspended). An open or
#: uncollectible invoice — or one with no status yet — that carries
#: `payment_failed_at` still stands.
SETTLED_PAYMENT_STATUSES = (USAGE_INVOICE_PAYMENT_STATUS_PAID,
                            USAGE_INVOICE_PAYMENT_STATUS_VOID)


def settle_failure_stamp(row, payment_status):
    """Clear ``row``'s `payment_failed_at` when ``payment_status`` (the row's
    applied status — `payment_status` on a usage invoice, `status` on a
    subscription invoice) is settled: paid, or void (§7 item 26). Call inside
    the transaction that holds the row's lock, before its save. Returns the
    row's HISTORICAL billing owner id when a stamp was cleared — its
    `historical_billing_owner_id`, the stored fact both invoice models answer
    by one name (a usage invoice's own `customer`, a subscription invoice's
    `billing_owner`; PLAN §7 item 27) — so the caller asks billing to clear
    that owner; else None, so a replayed paid/void delivery clears nothing
    twice. Row state only: it reads a stored column and resolves no owner, so
    no current topology can enter here. Shared by the webhook fast path and
    the hourly repair of both invoice tables. Only the stamp moves: a void row
    gains no `paid_at` and no paid amount."""
    if payment_status not in SETTLED_PAYMENT_STATUSES or row.payment_failed_at is None:
        return None
    row.payment_failed_at = None
    return row.historical_billing_owner_id
