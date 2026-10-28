"""A version-2 Pricing Receipt for the SDK's hand-built acknowledgements.

The recording acknowledgement publishes the receipt as a typed record since
#558 (R10-W4), version 2 only, and required: every recording writes one. A
rejected batch item carries null instead. One record here, so a fixture names
it rather than restating a shape it does not test.
"""

A_RECEIPT = {
    "receipt_schema_version": 2,
    "pricing_engine_version": "3.0.0",
    "subject_type": "usage_event",
    "subject_id": "evt_1",
    "effective_at": "2026-07-09T12:14:07+00:00",
    "currency": "usd",
    "costing": {"method": "calculated", "status": "known", "detail": {}},
    "pricing": {"method": "direct_event_price", "status": "known",
                "detail": {"pricing_mode": "event_priced"}},
    "totals": {"provider_cost_micros": 0, "billed_cost_micros": 0},
    "provenance": {},
}
