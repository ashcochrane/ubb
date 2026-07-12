# Billing-owned invoice routing helpers.
#
# Moved here from api/v1/webhooks.py to break the circular import:
# api/v1/webhooks.py eagerly imports handlers FROM
# apps/billing/connectors/stripe/webhooks.py, which means
# apps/billing can never safely import api/v1. Placing these
# helpers here (billing-domain logic they always were) lets both
# the webhook handler module and the invoicing task module import
# them directly, with zero circularity.

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
# payable and voidable; paid and void are genuinely final.
AR_ALLOWED = {
    "": {"open", "paid", "void", "uncollectible"},   # None/'' = no status yet
    "open": {"paid", "void", "uncollectible"},
    "uncollectible": {"paid", "void"},
    "paid": set(),
    "void": set(),
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
