"""A held name names the recorded event it arrived on (#568, #473).

One column and one index. Every held name now arrives beside a posting written
in the same savepoint — a quantity a declaration does not carry since #428, and
an Event Type with no production declaration since #568 — and a remediation has
to reach that posting to replay it from its own moment. The column is the id
the recording's acknowledgement publishes as `event_id`: an identity, not a
relation, because the kernel's table may not depend on a product's (ADR-001).

**Between the column and the rule that it is always there, a guard that
REFUSES and never invents.** A held row written before this migration cannot
say which event it arrived on, and nothing here can find out honestly: a tenant,
a name and an instant do not pick out one event, and a made-up id would point a
later replay at a posting that is not the one the name arrived on — or at none.
So the guard names every such row and stops, on #571's shape (`0009`). UBB is
deployed nowhere, so on the day this was written there was nothing for it to
find; it is what makes the column's `NOT NULL` honest rather than an assumption
about the tree.

The reverse removes the index and the column, and with the column every event
id a held name recorded: the tree it returns to is one where a held row could
not say which event it arrived on.
"""
from django.db import migrations, models


class HeldNameWithoutAnEvent(Exception):
    """A held row exists that cannot say which event it arrived on, and the
    rule about to be added would refuse it. The guard says which, rather than
    letting a constraint violation say nothing."""


def refuse_a_held_name_with_no_event(apps, schema_editor):
    """Name every held row by everything it takes to find it — the tenant's
    id and name, the held name, its moment and the row itself — and stop. It
    repairs nothing: which event a name arrived on is a fact this migration
    does not have."""
    QuarantinedKey = apps.get_model("event_types", "QuarantinedKey")
    found = [
        f"held {unrecognised} '{measurement_key or event_type_key}' "
        f"(QuarantinedKey {pk}) of tenant {tenant_id} ('{tenant_name}'), "
        f"arrived {occurred_at.isoformat()}"
        for (pk, tenant_id, tenant_name, unrecognised, event_type_key,
             measurement_key, occurred_at) in (
            QuarantinedKey.objects.filter(event_id__isnull=True)
            .order_by("tenant_id", "occurred_at", "pk")
            .values_list("pk", "tenant_id", "tenant__name", "unrecognised",
                         "event_type_key", "measurement_key", "occurred_at"))]
    if found:
        raise HeldNameWithoutAnEvent(
            f"event_types 0010 refuses to run: {len(found)} held "
            f"name{' does' if len(found) == 1 else 's do'} not say which "
            f"recorded event {'it' if len(found) == 1 else 'they'} arrived "
            f"on, and from this migration on every held name does, because a "
            f"remediation replays that event. UBB never invents one, and "
            f"repairs nothing. Found: {'; '.join(found)}. A pre-launch "
            f"database holding these is a development one: reset the sandbox "
            f"tenant (POST /api/v1/sandbox/reset), or delete the rows, then "
            f"migrate.")


class Migration(migrations.Migration):

    dependencies = [
        ("event_types", "0009_a_constant_declares_its_value"),
    ]

    operations = [
        migrations.AddField(
            model_name="quarantinedkey",
            name="event_id",
            field=models.UUIDField(null=True),
        ),
        migrations.RunPython(refuse_a_held_name_with_no_event,
                             migrations.RunPython.noop),
        migrations.AlterField(
            model_name="quarantinedkey",
            name="event_id",
            field=models.UUIDField(),
        ),
        migrations.AddIndex(
            model_name="quarantinedkey",
            index=models.Index(fields=["tenant", "event_id"],
                               name="ix_quarantined_key_event"),
        ),
    ]
