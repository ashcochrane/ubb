"""The OpenAPI 3.1 ``webhooks`` section: event catalog + frozen payload schemas.

Rides ``openapi/v1.json`` (and the runtime ``/api/v1/openapi.json``) via the
composed API's ``openapi_extra``, making catalog drift a CI failure at the
drift gate (ADR-002; subsumes the unit set-equality pin in
``tests/test_catalog.py``, which stays as defense in depth).

Sources of truth: ``catalog.WEBHOOK_EVENT_TYPES`` for the catalog,
``schemas.py``'s frozen dataclasses for payloads. Building refuses if the two
disagree, so the generated document can never advertise a catalog the payload
registry doesn't back.
"""
import dataclasses
import inspect

from pydantic import TypeAdapter

from apps.platform.events import schemas
from apps.platform.events.catalog import WEBHOOK_EVENT_TYPES

# The three delivery headers webhooks.py sends with every POST.
_HEADER_PARAMETERS = [
    {
        "name": "X-UBB-Signature-V2",
        "in": "header",
        "required": True,
        "schema": {"type": "string"},
        "description": (
            "`t=<unix-seconds>,v1=<hex>` — HMAC-SHA256 over "
            "`\"{t}.{body}\"` with the endpoint secret. Verify this one; "
            "during a future secret rotation window multiple `v1=` "
            "candidates may be present."
        ),
    },
    {
        "name": "X-UBB-Signature",
        "in": "header",
        "required": True,
        "schema": {"type": "string"},
        "description": (
            "Legacy body-only HMAC-SHA256 hex digest (no timestamp "
            "binding). Kept during the v2 deprecation window — prefer "
            "X-UBB-Signature-V2."
        ),
    },
    {
        "name": "X-UBB-Event-Type",
        "in": "header",
        "required": True,
        "schema": {"type": "string"},
        "description": "The event type, duplicated from the body for routing.",
    },
]


def _payload_schema_classes():
    """The frozen payload dataclasses defined in schemas.py (not imported in),
    keyed for the catalog comparison — the same enumeration the set-equality
    pin uses."""
    return [
        obj
        for obj in vars(schemas).values()
        if inspect.isclass(obj)
        and obj.__module__ == schemas.__name__
        and dataclasses.is_dataclass(obj)
        and isinstance(getattr(obj, "EVENT_TYPE", None), str)
    ]


def build_webhooks_section() -> dict:
    by_type = {cls.EVENT_TYPE: cls for cls in _payload_schema_classes()}
    if set(by_type) != set(WEBHOOK_EVENT_TYPES):
        missing = sorted(set(WEBHOOK_EVENT_TYPES) - set(by_type))
        extra = sorted(set(by_type) - set(WEBHOOK_EVENT_TYPES))
        raise RuntimeError(
            "webhook catalog and payload-schema registry disagree — "
            f"catalog-only: {missing}, schema-only: {extra}. Fix catalog.py "
            "or schemas.py before the document can be generated."
        )

    section = {}
    for event_type in sorted(WEBHOOK_EVENT_TYPES):
        payload_schema = TypeAdapter(by_type[event_type]).json_schema()
        envelope = {
            "type": "object",
            "properties": {
                "event_type": {"type": "string", "const": event_type},
                "event_id": {
                    "type": "string",
                    "description": (
                        "Unique event id. Delivery is at-least-once per "
                        "endpoint — receivers dedupe on it."
                    ),
                },
                "tenant_id": {"type": "string"},
                "timestamp": {
                    "type": "integer",
                    "description": (
                        "Unix seconds at send time; the same value is bound "
                        "into X-UBB-Signature-V2."
                    ),
                },
                "livemode": {
                    "type": "boolean",
                    "description": "False when the emitting tenant is a sandbox.",
                },
                "data": payload_schema,
            },
            "required": [
                "data",
                "event_id",
                "event_type",
                "livemode",
                "tenant_id",
                "timestamp",
            ],
        }
        section[event_type] = {
            "post": {
                "operationId": "webhook_" + event_type.replace(".", "_"),
                "summary": f"{event_type} delivery",
                "description": (
                    "Outbound POST to a subscribed webhook endpoint. Payload "
                    "fields are additive-only (frozen schema): new fields may "
                    "appear, existing ones never change meaning — receivers "
                    "must ignore unknown fields."
                ),
                "parameters": _HEADER_PARAMETERS,
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": envelope}},
                },
                "responses": {
                    "2XX": {
                        "description": (
                            "Any 2xx acknowledges the delivery; anything else "
                            "(or a timeout) is retried."
                        )
                    }
                },
            }
        }
    return section
