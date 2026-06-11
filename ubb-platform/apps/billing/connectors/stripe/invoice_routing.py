# Billing-owned invoice routing helpers.
#
# Moved here from api/v1/webhooks.py to break the circular import:
# api/v1/webhooks.py eagerly imports handlers FROM
# apps/billing/connectors/stripe/webhooks.py, which means
# apps/billing can never safely import api/v1. Placing these
# helpers here (billing-domain logic they always were) lets both
# the webhook handler module and the invoicing task module import
# them directly, with zero circularity.

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
