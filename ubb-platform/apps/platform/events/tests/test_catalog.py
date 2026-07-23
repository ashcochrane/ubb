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
    """Derivation check (#75 → #114): the catalog derives from the schema
    registry, so set-equality is structural — UNLESS a dataclass defined in
    schemas.py never registered because it forgot to inherit ``EventSchema``.
    This independent vars()-based enumeration catches exactly that residual
    drift (the base class already makes a missing/duplicate EVENT_TYPE an
    import-time error), keeping the #75 pin's intent: an event type present
    in the module but absent from the catalog is a red test, not the silent
    drift that hid customer.deleted from subscribers while the delivery path
    emitted it.
    """
    import dataclasses
    import inspect

    from apps.platform.events import schemas
    from apps.platform.events.catalog import WEBHOOK_EVENT_TYPES

    schema_classes = [
        obj
        for obj in vars(schemas).values()
        if inspect.isclass(obj)
        and obj.__module__ == schemas.__name__  # defined there, not imported in
        and dataclasses.is_dataclass(obj)
    ]
    # A schema class without an EVENT_TYPE would silently fall out of the
    # registry side of the set comparison — make that a red test too.
    missing_event_type = [
        cls.__name__
        for cls in schema_classes
        if not isinstance(getattr(cls, "EVENT_TYPE", None), str)
    ]
    assert missing_event_type == []

    schema_event_types = {cls.EVENT_TYPE for cls in schema_classes}
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
