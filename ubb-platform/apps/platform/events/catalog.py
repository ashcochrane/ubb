"""Canonical catalog of webhook-deliverable event types — derived, not listed.

Single source of truth for the events a tenant can subscribe a webhook to.
``apps.EventsConfig.ready()`` registers a delivery handler for each type here,
and the webhook config API validates submitted ``event_types`` against it, so
the registration and the public contract cannot drift apart.

The catalog DERIVES from the payload-schema registry (``schemas.py``): every
frozen payload dataclass IS the contract for one webhook-deliverable event,
so the two can no longer disagree (the drift class the old hand-listed tuple
needed pin tests to police — the #75 defect that hid ``customer.deleted``
from subscribers while the delivery path emitted it).

To add a new tenant-facing webhook event: add its frozen dataclass to
``schemas.py`` (and emit it to the outbox). That is the whole change — the
catalog, delivery registration, and the OpenAPI ``webhooks`` section all
follow. Do not register webhook delivery anywhere else.
"""
from apps.platform.events.schemas import payload_schema_classes

# Sentinel a tenant uses to subscribe to *all* events (Stripe's enabled_events
# convention). Stored verbatim in TenantWebhookConfig.event_types as ["*"].
WILDCARD = "*"

# Sorted for deterministic iteration; order is not significant.
WEBHOOK_EVENT_TYPES = tuple(
    sorted(cls.EVENT_TYPE for cls in payload_schema_classes())
)

_WEBHOOK_EVENT_TYPES_SET = frozenset(WEBHOOK_EVENT_TYPES)


def is_valid_event_selector(value: str) -> bool:
    """True if ``value`` is the wildcard or a known event type.

    Used to validate a tenant's requested ``event_types`` at config-create time
    so a typo (e.g. ``"usage.recieved"``) is rejected loudly instead of silently
    matching nothing forever.
    """
    return value == WILDCARD or value in _WEBHOOK_EVENT_TYPES_SET
