"""Canonical catalog of webhook-deliverable event types.

Single source of truth for the events a tenant can subscribe a webhook to.
``apps.EventsConfig.ready()`` registers a delivery handler for each type here,
and the webhook config API validates submitted ``event_types`` against it, so
the registration and the public contract cannot drift apart.

To add a new tenant-facing webhook event: add its type string here (and emit it
to the outbox). Do not register webhook delivery anywhere else.
"""

# Sentinel a tenant uses to subscribe to *all* events (Stripe's enabled_events
# convention). Stored verbatim in TenantWebhookConfig.event_types as ["*"].
WILDCARD = "*"

# Order is not significant — grouped by namespace for readability.
WEBHOOK_EVENT_TYPES = (
    # usage / metering
    "usage.recorded",
    "usage.refunded",
    "usage.invoice_pushed",
    "usage.invoice_push_failed_permanent",
    "refund.requested",
    # billing / wallet
    "billing.balance_low",
    "billing.balance_critical",
    "billing.balance_overage",
    "billing.topup_requested",
    "billing.withdrawal_requested",
    "billing.customer_suspended",
    "billing.credit_grant_expiring",
    "billing.credit_grant_expired",
    "auto_topup.requires_action",
    # budgets / tasks
    "budget.threshold_reached",
    "task.limit_exceeded",
    "subtask.limit_exceeded",
    "stop.fired",
    "stop.cleared",
    # margins / economics
    "margin.customer_unprofitable",
    "margin.provider_cost_spike",
    # referrals
    "referral.created",
    "referral.reward_earned",
    "referral.expired",
    "referral.payout_due",
    # platform / lifecycle
    "sandbox.reset_completed",
    "tenant.api_key_created",
    "tenant.api_key_rotated",
    "tenant.api_key_revoked",
)

_WEBHOOK_EVENT_TYPES_SET = frozenset(WEBHOOK_EVENT_TYPES)


def is_valid_event_selector(value: str) -> bool:
    """True if ``value`` is the wildcard or a known event type.

    Used to validate a tenant's requested ``event_types`` at config-create time
    so a typo (e.g. ``"usage.recieved"``) is rejected loudly instead of silently
    matching nothing forever.
    """
    return value == WILDCARD or value in _WEBHOOK_EVENT_TYPES_SET
