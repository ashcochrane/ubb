"""Stamp every queued `usage.recorded` payload with `pricing_status_reason`
(#603, ADR-0020).

The payload gains the registry's `pricing_status_reason` as a REQUIRED,
nullable field — the owner's rule wherever `pricing_status` is published
(`6279966961`) — and `events/schemas.py` admits a required payload field only
once every stored row and queued payload carries it (`_TerminalStop.
control_family`, `work/migrations/0027`, is the precedent). An outbox row is a
work queue: `UsageRecorded.from_payload` builds the consumer's view of it, and a
required field missing from a row written before this commit would be a loud
`TypeError` in an outbox handler, retried with backoff.

**Every such row gets null, and null is the honest value.** A payload written
before #603 was written by an engine that never recorded a negative price as
unresolved — a negative quantity could not be recorded at all — so no row
written then can carry the reason, and "no published reason applies" is
exactly what it means.

**What is touched and what is not**, on `0009`'s reasoning: only the outbox
rows of this one event type, and only those missing the key. A delivery
attempt is the record of what a subscriber actually received, and its body
keeps what was sent.

The reverse removes the key from every `usage.recorded` row, so the payloads
read as they did before.
"""
from django.db import migrations

EVENT_TYPE = "usage.recorded"
KEY = "pricing_status_reason"


def stamp(apps, schema_editor):
    OutboxEvent = apps.get_model("events", "OutboxEvent")
    for row in OutboxEvent.objects.filter(event_type=EVENT_TYPE).only(
            "id", "payload").iterator():
        if isinstance(row.payload, dict) and KEY not in row.payload:
            OutboxEvent.objects.filter(pk=row.pk).update(
                payload={**row.payload, KEY: None})


def unstamp(apps, schema_editor):
    OutboxEvent = apps.get_model("events", "OutboxEvent")
    for row in OutboxEvent.objects.filter(event_type=EVENT_TYPE).only(
            "id", "payload").iterator():
        if isinstance(row.payload, dict) and KEY in row.payload:
            payload = dict(row.payload)
            del payload[KEY]
            OutboxEvent.objects.filter(pk=row.pk).update(payload=payload)


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0009_five_control_events_move_under_their_families"),
    ]

    operations = [
        migrations.RunPython(stamp, unstamp),
    ]
