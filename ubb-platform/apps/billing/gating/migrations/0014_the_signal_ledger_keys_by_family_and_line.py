"""The signal ledger keys by family and line (#458, slice 6 §9, ADR-0007 §1).

The ledger held one row per owner per LOCAL family word — `floor_stop` for
the customer-wide hard stop, which both the wallet's hard floor and the
customer spend pool opened, and `soft_floor` for the wind-down signal — and
its `reason` column carried the stop's word while stopped and the clearing
cause once cleared. The registry's `control_family` names the control now,
and the ledger's key becomes (owner, `control_family`, `reason`) where
`reason` is the ledger's own LINE: `hard_floor` and `customer_spend_pool`
for the two stop lines, `soft_floor` for the wind-down line. Three lines,
each with its own episode sequence, so a customer stopped by its pool and by
its floor at once holds two independent episodes.

  * `family` is RENAMED to `control_family` (`RenameField`, carrying every
    row) and its values rewritten: a `floor_stop` row becomes the pool's
    (`customer_spend_pool`) where the owner's tenant is postpaid and the
    wallet policy's (`wallet_policy`) otherwise; a `soft_floor` row becomes
    the wallet policy's.
  * `reason` becomes the line — the stop word the row's control produces,
    `soft_floor` on the wind-down line — and what it held on a CLEARED row
    (the clearing cause) moves to the new `clear_reason` column, so the line
    can be part of the key.
  * `control_id` arrives empty: which row declared the control that opened a
    historical episode was never recorded, and inventing one now would be a
    guess published on every re-mint. Every episode opened after this
    migration records it.
  * the unique key moves from (owner, family) to (owner, `control_family`,
    `reason`) — dropped before the rename and re-added after the data pass,
    because it carries no data. No two old rows collide under the new key:
    an owner had at most one row per old family, and the two old families
    map to two different lines.
  * the customer stop pair's queued outbox payloads take the new shape: the
    bare `reason` becomes `reason_code` — the line's word, which on a
    `stop.cleared` row replaces the clearing cause the old key carried —
    and `control_family` is derived from it; `control_id` is empty for the
    reason the column is. Scoped by EVENT TYPE (#457's lesson): `reason` is
    free text on other events and is left as written there.

**⚠ THE SPLIT IS ROUTED BY THE OWNER'S TENANT BILLING MODE**, which is the only
fact a historical row can answer with — the same fork `work/migrations/0026`
used for the stored stop cause, spelled here rather than imported because a
migration must keep working when the code has moved on. The producers no
longer fork at all: each lane names its own line (#458 deleted
`reasons.customer_stop_reason`), and this is the last place the fork is
spelled.

**The reverse is provided and is LOSSY in two named places**: a `stop.cleared`
payload's clearing cause does not come back (the forward replaced it with the
line's word and the cause survives only on the ledger row), and the
wind-down line's stopped `reason` comes back as the start-gate word the old
row carried. Everything else round-trips exactly: the two old families are
functions of the new (family, line), and a cleared row's `reason` is its
`clear_reason` again. Nothing is deployed; the rows this touches exist on
developer machines and in fixtures only.
"""
from django.db import migrations, models

#: A second encoding of names the registry declares, necessarily so: a
#: migration must not import application code. The gating app's own test
#: for this migration holds every value below to the constants.
FAMILY_CEILING = "ceiling"
FAMILY_CUSTOMER_SPEND_POOL = "customer_spend_pool"
FAMILY_WALLET_POLICY = "wallet_policy"
FAMILY_ADMISSION_CONTROL = "admission_control"

LINE_HARD_FLOOR = "hard_floor"
LINE_CUSTOMER_SPEND_POOL = "customer_spend_pool"
LINE_SOFT_FLOOR = "soft_floor"

#: The two local family words the ledger used until now.
OLD_FLOOR_STOP = "floor_stop"
OLD_SOFT_FLOOR = "soft_floor"
#: The start-gate word the old wind-down row carried while stopped.
OLD_SOFT_FLOOR_REACHED = "soft_floor_reached"

STATE_CLEARED = "cleared"
POSTPAID = "postpaid"

#: The customer stop pair — the only events this migration reads.
STOP_FIRED = "stop.fired"
STOP_CLEARED = "stop.cleared"
PAIR = (STOP_FIRED, STOP_CLEARED)

CONTROL_FAMILY_CHOICES = [
    (FAMILY_CEILING, "Ceiling"),
    (FAMILY_CUSTOMER_SPEND_POOL, "Customer spend pool"),
    (FAMILY_WALLET_POLICY, "Wallet policy"),
    (FAMILY_ADMISSION_CONTROL, "Admission control"),
]


def stop_line(billing_mode):
    """Which stop line a historical customer-wide episode belongs to."""
    return LINE_CUSTOMER_SPEND_POOL if billing_mode == POSTPAID else LINE_HARD_FLOOR


def family_of_line(line):
    return (FAMILY_CUSTOMER_SPEND_POOL if line == LINE_CUSTOMER_SPEND_POOL
            else FAMILY_WALLET_POLICY)


def _modes(apps):
    Tenant = apps.get_model("tenants", "Tenant")
    return dict(Tenant.objects.values_list("id", "billing_mode"))


def _key_the_lines(apps, schema_editor):
    """Forward: every row onto (family, line, clear_reason); every queued
    pair payload onto (reason_code, control_family, control_id)."""
    StopSignalState = apps.get_model("gating", "StopSignalState")
    OutboxEvent = apps.get_model("events", "OutboxEvent")
    modes = _modes(apps)

    for row in StopSignalState.objects.only(
            "id", "tenant_id", "control_family", "reason", "state").iterator():
        if row.control_family == OLD_SOFT_FLOOR:
            line = LINE_SOFT_FLOOR
        else:
            line = stop_line(modes.get(row.tenant_id))
        StopSignalState.objects.filter(pk=row.pk).update(
            control_family=family_of_line(line), reason=line,
            clear_reason=row.reason if row.state == STATE_CLEARED else "")

    for event in (OutboxEvent.objects
                  .filter(event_type__in=PAIR, payload__has_key="reason")
                  .only("id", "tenant_id", "payload").iterator()):
        payload = dict(event.payload)
        payload.pop("reason")
        line = stop_line(modes.get(event.tenant_id))
        payload.update(reason_code=line, control_family=family_of_line(line),
                       control_id="")
        OutboxEvent.objects.filter(pk=event.pk).update(payload=payload)


def _collapse_the_lines(apps, schema_editor):
    """Reverse, lossily — the module docstring names the two places."""
    StopSignalState = apps.get_model("gating", "StopSignalState")
    OutboxEvent = apps.get_model("events", "OutboxEvent")

    for row in StopSignalState.objects.only(
            "id", "reason", "clear_reason", "state").iterator():
        soft = row.reason == LINE_SOFT_FLOOR
        if row.state == STATE_CLEARED:
            reason = row.clear_reason
        else:
            reason = OLD_SOFT_FLOOR_REACHED if soft else row.reason
        StopSignalState.objects.filter(pk=row.pk).update(
            control_family=OLD_SOFT_FLOOR if soft else OLD_FLOOR_STOP,
            reason=reason, clear_reason="")

    for event in (OutboxEvent.objects
                  .filter(event_type__in=PAIR, payload__has_key="reason_code")
                  .only("id", "payload").iterator()):
        payload = dict(event.payload)
        payload["reason"] = payload.pop("reason_code")
        payload.pop("control_family", None)
        payload.pop("control_id", None)
        OutboxEvent.objects.filter(pk=event.pk).update(payload=payload)


class Migration(migrations.Migration):

    dependencies = [
        ("gating", "0013_the_pool_row_takes_the_family_name"),
        ("events", "0008_the_two_terminal_task_events_become_four"),
        ("tenants", "0026_the_default_ceilings_for_undeclared_work_come_to_the_kernel"),
    ]

    operations = [
        # The old key carries no data: dropped before the rename it names.
        migrations.RemoveConstraint(
            model_name="stopsignalstate", name="uq_stop_signal_owner_family"),
        # THE COLUMN, CARRYING ITS ROWS (ADR-0007 §1) — then its values.
        migrations.RenameField(
            model_name="stopsignalstate", old_name="family",
            new_name="control_family"),
        migrations.AlterField(
            model_name="stopsignalstate", name="control_family",
            field=models.CharField(choices=CONTROL_FAMILY_CHOICES, max_length=20)),
        migrations.AlterField(
            model_name="stopsignalstate", name="reason",
            field=models.CharField(max_length=64)),
        migrations.AddField(
            model_name="stopsignalstate", name="clear_reason",
            field=models.CharField(blank=True, default="", max_length=64)),
        migrations.AddField(
            model_name="stopsignalstate", name="control_id",
            field=models.UUIDField(blank=True, null=True)),
        migrations.RunPython(_key_the_lines, _collapse_the_lines),
        migrations.AddConstraint(
            model_name="stopsignalstate",
            constraint=models.UniqueConstraint(
                fields=("owner", "control_family", "reason"),
                name="uq_stop_signal_owner_family_line"),
        ),
    ]
