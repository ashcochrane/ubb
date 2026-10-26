"""A unit's stop and its start are UBB's own record (R10-W2: #551, #540).

Two facts UBB publishes about a unit of work move onto columns UBB alone writes,
and the database holds both as written-once records.

**1. WHAT UBB RECORDED WHEN IT STOPPED THE UNIT.** The cause (`reason_code`),
the mechanism (`trigger_source`), the control's family (`control_family`) and
its identity (`control_id`) were keys of those spellings inside
`Task.metadata` — which is also the caller's own bag from the start. So a
caller could plant `reason_code`, and the only thing keeping it from reading as
UBB's was that every terminal path overwrote or scrubbed the key. The unit read
publishes these three as UBB's assertions (#551); a caller-writable bag cannot
be their source. They are four columns now, nothing a caller sends reaches
them, and `metadata` is the caller's bag alone.

  * Every `killed` and `expired` row has its four keys MOVED out of `metadata`
    into the columns (an empty value becomes NULL). Those are the rows UBB's
    stops wrote them on, overwriting anything of the caller's.
  * A `cancelled` piece of contained work its parent's close withdrew
    (`outcome_reason: parent_closed`) has the cascade's `parent_cascade`
    mechanism moved too — the cascade stamps it on every piece it withdraws.
  * Every other row is left alone: a key of one of these spellings on a unit
    UBB never stopped is the caller's own, and stays in the caller's bag.

⚠ ONE AMBIGUITY, STATED. A unit the hourly safety net expired silently before
this window carried no key of UBB's, so any key on it was the caller's — and it
is moved like the rest, because the row cannot say whose it was. Nothing is
deployed (the rows exist on developer machines and in fixtures), and W6's squash
starts a fresh database, so no deployed unit is misread.

**2. THE EXPIRY POLICY THE START PUBLISHED.** A start answers with the unit's
absolute deadline and silence window as the ladder resolves them (#540); the
sweepers deliberately re-resolve that ladder each time they run, so a changed
window reaches running work. A replay of the start must answer what the start
said (ADR-0019's rule for an acknowledgement; `StartTaskResponse`'s own "on a
replay this is the original attempt's number"), so the start snapshots the two
resolved durations (`start_absolute_deadline_seconds`,
`start_silence_window_seconds`) and the response reads them back. Existing rows
are given the policy as the ladder resolves it NOW — the instant each was
started is past recovery, and nothing is deployed.

**3. THE RULE.** `trg_task_declared_transitions` (installed by `0028`) is
widened, not joined: the four stop facts are SET_ONCE — NULL to a value, once;
UBB never rewrites a stop it recorded — and the two snapshot columns FROZEN.
The `WHEN` clause names all eleven columns, so the hot writes still never enter
the function. Same name, same SQLSTATE `23000`, each message opening
`<column> is declared <class>`.

**THE REVERSE** reinstalls `0028`'s rule, puts every moved fact back into
`metadata` under its old key and drops the columns.
"""
import importlib

from django.db import migrations, models

#: Spelled here because a migration must not import application code; the
#: work app's tests hold each to the registry and the model.
UBB_STOPPED_STATUSES = ("killed", "expired")
CANCELLED = "cancelled"
PARENT_CLOSED = "parent_closed"
PARENT_CASCADE = "parent_cascade"
STOP_FACTS = ("reason_code", "trigger_source", "control_family", "control_id")
KIND_TASK = "task"
KIND_SUBTASK = "subtask"
SILENCE_WINDOW_BACKSTOP_SECONDS = 15 * 60
ABSOLUTE_DEADLINE_BACKSTOP_SECONDS = 6 * 60 * 60

PREVIOUS = importlib.import_module(
    "apps.platform.work.migrations.0028_a_unit_of_work_is_born_once_and_ends_once")
TRIGGER = PREVIOUS.TRIGGER
FUNCTION = PREVIOUS.FUNCTION
UNRESOLVED_STATUS = PREVIOUS.UNRESOLVED_STATUS


def _fact(value):
    return str(value) if value not in (None, "") else None


def move_the_stop_facts_out_of_the_callers_bag(apps, schema_editor):
    Task = apps.get_model("work", "Task")
    for task in Task.objects.filter(status__in=UBB_STOPPED_STATUSES).iterator():
        bag = dict(task.metadata or {})
        for key in STOP_FACTS:
            setattr(task, key, _fact(bag.pop(key, None)))
        task.metadata = bag
        task.save(update_fields=[*STOP_FACTS, "metadata"])
    withdrawn = Task.objects.filter(status=CANCELLED, parent__isnull=False,
                                    outcome_reason=PARENT_CLOSED)
    for task in withdrawn.iterator():
        bag = dict(task.metadata or {})
        if bag.get("trigger_source") == PARENT_CASCADE:
            del bag["trigger_source"]
            task.trigger_source = PARENT_CASCADE
            task.metadata = bag
            task.save(update_fields=["trigger_source", "metadata"])


def put_the_stop_facts_back(apps, schema_editor):
    Task = apps.get_model("work", "Task")
    recorded = models.Q()
    for key in STOP_FACTS:
        recorded |= models.Q(**{f"{key}__isnull": False})
    for task in Task.objects.filter(recorded).iterator():
        bag = dict(task.metadata or {})
        for key in STOP_FACTS:
            value = getattr(task, key)
            if value is not None:
                bag[key] = value
            setattr(task, key, None)
        task.metadata = bag
        task.save(update_fields=[*STOP_FACTS, "metadata"])


def _rung(declared, beneath):
    """`work.queries._rung`, spelled again: NULL falls through, 0 is "none"."""
    if declared is None:
        return beneath
    if declared == 0:
        return None
    return declared


def snapshot_the_expiry_of_every_unit(apps, schema_editor):
    """The ladder `work.queries.expiry_windows` climbs — the declared kind of
    work at the unit's own altitude, then the tenant's default, then UBB's
    backstop — resolved now for every unit that has no snapshot."""
    Task = apps.get_model("work", "Task")
    TaskType = apps.get_model("work", "TaskType")
    Tenant = apps.get_model("tenants", "Tenant")
    tenants = {tenant.id: tenant for tenant in Tenant.objects.only(
        "id", "task_stale_seconds", "task_absolute_deadline_seconds")}
    kinds = {(kind.tenant_id, kind.kind, kind.key): kind
             for kind in TaskType.objects.all()}
    for task in Task.objects.filter(
            start_absolute_deadline_seconds__isnull=True).iterator():
        tenant = tenants[task.tenant_id]
        silence = _rung(tenant.task_stale_seconds, SILENCE_WINDOW_BACKSTOP_SECONDS)
        absolute = _rung(tenant.task_absolute_deadline_seconds,
                         ABSOLUTE_DEADLINE_BACKSTOP_SECONDS)
        kind = kinds.get((task.tenant_id,
                          KIND_SUBTASK if task.parent_id else KIND_TASK,
                          task.task_type))
        if kind is not None:
            silence = _rung(kind.silence_window_seconds, silence)
            absolute = _rung(kind.absolute_deadline_seconds, absolute)
        task.start_absolute_deadline_seconds = absolute
        task.start_silence_window_seconds = silence
        task.save(update_fields=["start_absolute_deadline_seconds",
                                 "start_silence_window_seconds"])


def _set_once(column, why):
    return f"""
    IF OLD.{column} IS NOT NULL AND NEW.{column} IS DISTINCT FROM OLD.{column} THEN
        RAISE EXCEPTION
            '{column} is declared set_once (ADR-0007 §2): {why}. Got % to %',
            OLD.{column}, NEW.{column}
            USING ERRCODE = '23000';
    END IF;
"""


def _frozen(column, why):
    return f"""
    IF NEW.{column} IS DISTINCT FROM OLD.{column} THEN
        RAISE EXCEPTION
            '{column} is declared frozen (ADR-0007 §2): {why}. Got % to %',
            OLD.{column}, NEW.{column}
            USING ERRCODE = '23000';
    END IF;
"""


STOP_FACT_WHY = "a stop UBB recorded is never rewritten"
SNAPSHOT_WHY = "it is the expiry policy the start published, and a replay repeats it"

#: `0028`'s five refusals, then the six this migration adds.
WIDENED_BODY = (
    PREVIOUS.REFUSALS
    + "".join(_set_once(column, STOP_FACT_WHY) for column in STOP_FACTS)
    + _frozen("start_absolute_deadline_seconds", SNAPSHOT_WHY)
    + _frozen("start_silence_window_seconds", SNAPSHOT_WHY))

WATCHED = ("status", "parent_id", "task_type", "outcome_reason", "reason_detail",
           *STOP_FACTS, "start_absolute_deadline_seconds",
           "start_silence_window_seconds")

INSTALL = f"""
DROP TRIGGER {TRIGGER} ON ubb_task;
CREATE OR REPLACE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN{WIDENED_BODY}
    RETURN NEW;
END;
$$;

CREATE TRIGGER {TRIGGER}
BEFORE UPDATE ON ubb_task
FOR EACH ROW
WHEN ({" OR ".join(f"OLD.{column} IS DISTINCT FROM NEW.{column}" for column in WATCHED)})
EXECUTE FUNCTION {FUNCTION}();
"""


def install(apps, schema_editor):
    schema_editor.execute(INSTALL, params=None)


def reinstall_the_previous_rule(apps, schema_editor):
    schema_editor.execute(PREVIOUS.UNINSTALL, params=None)
    schema_editor.execute(PREVIOUS.INSTALL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0025_the_two_expiry_windows_get_a_tenant_rung'),
        ('work', '0028_a_unit_of_work_is_born_once_and_ends_once'),
    ]

    operations = [
        migrations.AddField(
            model_name='task', name='reason_code',
            field=models.CharField(blank=True, max_length=64, null=True)),
        migrations.AddField(
            model_name='task', name='trigger_source',
            field=models.CharField(blank=True, max_length=64, null=True)),
        migrations.AddField(
            model_name='task', name='control_family',
            field=models.CharField(blank=True, max_length=64, null=True)),
        migrations.AddField(
            model_name='task', name='control_id',
            field=models.CharField(blank=True, max_length=64, null=True)),
        migrations.AddField(
            model_name='task', name='start_absolute_deadline_seconds',
            field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField(
            model_name='task', name='start_silence_window_seconds',
            field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.RunPython(move_the_stop_facts_out_of_the_callers_bag,
                             put_the_stop_facts_back),
        migrations.RunPython(snapshot_the_expiry_of_every_unit,
                             migrations.RunPython.noop),
        migrations.RunPython(install, reinstall_the_previous_rule),
    ]
