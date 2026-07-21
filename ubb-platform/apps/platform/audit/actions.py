"""The audit action registry — the contractual vocabulary of recordable actions.

Each recorded action is a stable, domain-shaped name (``noun.verb``) that is part
of the public compatibility contract (ADR-004 §2, under ADR-003's rules):
**additive-only, a rename is a breaking change**. Names are deliberately decoupled
from routes — the ADR-002 single-API restructure renames routes; it must never
rewrite history's vocabulary — and equally decoupled from the webhook catalog
(``apps/platform/events/catalog.py``): queue and ledger stay separate concepts, so
the audit action ``api_key.created`` and the webhook event ``tenant.api_key_created``
are independent names in independent contracts.

This is the audit twin of that catalog and the #63 error-code registry: one source
of truth, extended only by appending. ``record()`` refuses an unregistered name, so
the registry cannot silently drift from what the ledger actually writes — and the
#82 mutating-route CI pin checks new routes against exactly this set.
"""

# Order is not significant — grouped by namespace for readability. #81 landed the
# ledger and one real site (api-key mint); #82 sweeps the rest of the mutating
# surface in, appending here. Every name below is written by exactly one route (a
# few — budget.set, markup.set, top_up.requested — by the tenant/customer or
# tenant/widget twins of one operation). Usage ingestion (record_usage[/batch],
# ingest, task close) and the spend pre-check are telemetry, not governance, and
# deliberately have NO action here — see the exemption list in
# api/v1/tests/test_audit_sweep.py.
AUDIT_ACTIONS = (
    # api keys / credentials (membership + key lifecycle)
    "api_key.created",
    "api_key.rotated",
    "api_key.revoked",
    # members & invitations (identity, #79/#80)
    "invitation.created",
    "invitation.revoked",
    "member.role_changed",
    "member.removed",
    # tenant governance / config
    "tenant.config_changed",
    "sandbox.created",
    "sandbox.reset",
    "connect.started",
    # spend-control config
    "budget.set",
    "billing_profile.set",
    "auto_top_up.configured",
    "postpaid_config.set",
    # hand-moved money
    "wallet.credited",
    "wallet.debited",
    "wallet.withdrawn",
    # A top-up is recorded at INITIATION (a pending attempt) — the crediting is
    # system-driven and lands later via the PaymentIntent path — so the name
    # says "requested", not "topped_up".
    "top_up.requested",
    "usage.refunded",
    "grant.created",
    "grant.voided",
    # pricing / rate cards
    "rate_card.created",
    "rate_card.assigned",
    "rate_card.published",
    "rate.added",
    "rate.deleted",
    "markup.set",
    "markup.deleted",
    # margin / revenue
    "margin_threshold.set",
    "revenue_profile.set",
    "revenue_mode.set",
    # customers & subscriptions
    "customer.created",
    "plan.created",
    "plan.updated",
    "subscription.created",
    "subscription.canceled",
    "subscription.paused",
    "subscription.resumed",
    "subscription.seats_changed",
    # referrals
    "referral_program.created",
    "referral_program.updated",
    "referral_program.deactivated",
    "referral_program.reactivated",
    "referrer.registered",
    "referral.attributed",
    "referral.revoked",
    # webhook configuration
    "webhook_config.created",
    "webhook_config.deleted",
)

_AUDIT_ACTIONS_SET = frozenset(AUDIT_ACTIONS)


def is_registered_action(name):
    """True if ``name`` is a registered audit action."""
    return name in _AUDIT_ACTIONS_SET
