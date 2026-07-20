"""Tests for the canonical webhook event-type catalog.

The catalog is the single source of truth: apps.py registers delivery
handlers from it, and the webhook config API validates against it. These
tests lock that invariant so the two cannot drift apart.
"""


def test_catalog_is_exactly_what_registers_webhook_delivery():
    """Every catalog type — and only those — has the webhook delivery handler."""
    from apps.platform.events.registry import handler_registry
    from apps.platform.events.webhooks import handle_webhook_delivery
    from apps.platform.events.catalog import WEBHOOK_EVENT_TYPES

    registered = {
        event_type
        for event_type, handlers in handler_registry._handlers.items()
        if any(h["handler"] is handle_webhook_delivery for h in handlers)
    }
    assert registered == set(WEBHOOK_EVENT_TYPES)


def test_catalog_is_set_equal_to_frozen_payload_schema_registry():
    """Bridge pin (#75): set(catalog) == set(payload-schema event types).

    Every frozen dataclass in schemas.py IS the payload contract for a
    webhook-deliverable event, so an event type added to one side but not
    the other is a red test, not silent drift — the defect that hid
    customer.deleted from subscribers while the delivery path emitted it.
    Stage 1's OpenAPI ``webhooks`` section subsumes this behind the drift
    gate; this unit pin stays as defense in depth.
    """
    import dataclasses
    import inspect

    from apps.platform.events import schemas
    from apps.platform.events.catalog import WEBHOOK_EVENT_TYPES

    schema_event_types = {
        obj.EVENT_TYPE
        for obj in vars(schemas).values()
        if inspect.isclass(obj)
        and dataclasses.is_dataclass(obj)
        and isinstance(getattr(obj, "EVENT_TYPE", None), str)
    }
    assert schema_event_types == set(WEBHOOK_EVENT_TYPES)


def test_no_duplicate_event_types():
    from apps.platform.events.catalog import WEBHOOK_EVENT_TYPES

    assert len(WEBHOOK_EVENT_TYPES) == len(set(WEBHOOK_EVENT_TYPES))


def test_is_valid_event_selector_accepts_known_types_and_wildcard():
    from apps.platform.events.catalog import is_valid_event_selector

    assert is_valid_event_selector("usage.recorded") is True
    assert is_valid_event_selector("customer.deleted") is True
    assert is_valid_event_selector("*") is True


def test_is_valid_event_selector_rejects_unknown_and_empty():
    from apps.platform.events.catalog import is_valid_event_selector

    assert is_valid_event_selector("bogus.event") is False
    assert is_valid_event_selector("") is False
