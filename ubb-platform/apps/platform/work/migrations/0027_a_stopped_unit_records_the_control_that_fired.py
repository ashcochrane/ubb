"""A stopped unit records the control that fired (#458, slice 6 §1, §15).

Every stopped unit carries its cause (`reason_code`) and the mechanism that
applied it (`trigger_source`) in its metadata; from #458 the kernel also
stamps WHICH CONTROL's bound was reached — its family (`control_family`) and
the row that declares it (`control_id`) — on the winning flip and on every
cascaded piece, and the terminal stop announcement, the patrol's re-mint and
the four terminal payloads carry both, with the ceiling's basis derived off
the cause. The payload's family field is a CLOSED vocabulary with no honest
default, so it is required on the wire — and a required field asks that
every stored row and every queued payload already carry it, which is what
this migration gives them.

  * every unit row holding a stop cause is stamped `control_family: ceiling`
    — every stop UBB has ever applied to a UNIT was a ceiling's (the COGS
    ceiling or a window), and every cascade under one inherits the parent's,
    so the family is not a guess — and `control_id`: the declaration the
    unit runs under (the kind of work's row at the unit's altitude) or the
    tenant's own id for an undeclared unit on the tenant rung, resolved as
    the kernel resolves it today (`services.ceiling_control_id`);
  * every queued payload of the four terminal stop events is stamped the
    same family, the id its unit row now carries, and `ceiling_basis` off
    its own `reason_code` (`cost` for the ceiling, `time` for either window,
    null for a cascade word, which no announced payload carries).

The reverse removes the three keys from rows and payloads, which
round-trips exactly. Nothing is deployed; the rows this touches exist on
developer machines and in fixtures only.
"""
from django.db import migrations

#: A second encoding of names the registry and the kernel declare, necessarily
#: so: a migration must not import application code. The work app's test for
#: this migration holds every value below to the constants.
CAUSE_KEY = "reason_code"
FAMILY_KEY = "control_family"
CONTROL_KEY = "control_id"

FAMILY_CEILING = "ceiling"
BASIS_COST = "cost"
BASIS_TIME = "time"

#: Cause → basis, for the causes a ceiling produces; anything else has none.
BASIS_BY_CAUSE = {
    "task_cogs_ceiling": BASIS_COST,
    "silence_window": BASIS_TIME,
    "absolute_deadline": BASIS_TIME,
}

TERMINAL_STOP_EVENTS = (
    "task.killed", "task.expired", "subtask.killed", "subtask.expired",
)

KIND_TASK = "task"
KIND_SUBTASK = "subtask"


def _declarations(apps):
    TaskType = apps.get_model("work", "TaskType")
    return {(row["tenant_id"], row["kind"], row["key"]): str(row["id"])
            for row in TaskType.objects.values("id", "tenant_id", "kind", "key")}


def control_id_of(task, declarations):
    """The declaration the unit runs under, else the tenant — the kernel's
    own resolution, spelled for the historical rows."""
    if task.task_type:
        kind = KIND_SUBTASK if task.parent_id else KIND_TASK
        declared = declarations.get((task.tenant_id, kind, task.task_type))
        if declared is not None:
            return declared
    return str(task.tenant_id)


def _stamp_the_control(apps, schema_editor):
    Task = apps.get_model("work", "Task")
    OutboxEvent = apps.get_model("events", "OutboxEvent")
    declarations = _declarations(apps)

    controls = {}
    for task in (Task.objects.filter(metadata__has_key=CAUSE_KEY)
                 .only("id", "tenant_id", "parent_id", "task_type", "metadata")
                 .iterator()):
        control = control_id_of(task, declarations)
        controls[str(task.id)] = control
        if task.metadata.get(FAMILY_KEY) and task.metadata.get(CONTROL_KEY):
            continue
        Task.objects.filter(pk=task.pk).update(metadata={
            **task.metadata, FAMILY_KEY: FAMILY_CEILING, CONTROL_KEY: control})

    for event in (OutboxEvent.objects
                  .filter(event_type__in=TERMINAL_STOP_EVENTS)
                  .only("id", "payload").iterator()):
        payload = event.payload
        if FAMILY_KEY in payload:
            continue
        unit = payload.get("subtask_id") or payload.get("task_id") or ""
        OutboxEvent.objects.filter(pk=event.pk).update(payload={
            **payload,
            FAMILY_KEY: FAMILY_CEILING,
            CONTROL_KEY: controls.get(unit, ""),
            "ceiling_basis": BASIS_BY_CAUSE.get(payload.get(CAUSE_KEY))})


def _forget_the_control(apps, schema_editor):
    Task = apps.get_model("work", "Task")
    OutboxEvent = apps.get_model("events", "OutboxEvent")

    for task in (Task.objects.filter(metadata__has_key=FAMILY_KEY)
                 .only("id", "metadata").iterator()):
        metadata = {k: v for k, v in task.metadata.items()
                    if k not in (FAMILY_KEY, CONTROL_KEY)}
        Task.objects.filter(pk=task.pk).update(metadata=metadata)

    for event in (OutboxEvent.objects
                  .filter(event_type__in=TERMINAL_STOP_EVENTS,
                          payload__has_key=FAMILY_KEY)
                  .only("id", "payload").iterator()):
        payload = {k: v for k, v in event.payload.items()
                   if k not in (FAMILY_KEY, CONTROL_KEY, "ceiling_basis")}
        OutboxEvent.objects.filter(pk=event.pk).update(payload=payload)


class Migration(migrations.Migration):

    dependencies = [
        ("work", "0026_a_stop_says_which_bound_was_reached"),
        ("events", "0008_the_two_terminal_task_events_become_four"),
    ]

    operations = [
        migrations.RunPython(_stamp_the_control, _forget_the_control),
    ]
