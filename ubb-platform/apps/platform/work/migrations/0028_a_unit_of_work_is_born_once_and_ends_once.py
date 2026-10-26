"""A unit of work is born once and ends once, and the table holds both (#562).

One rule over five columns. `Task.transition_classes` declares them — ADR-0007
§2's classes, the model's own prose made a mapping — and ADR-0007 §2 is explicit
that declaring is not enforcing: *"a model-level guard alone is not
enforcement; the repository has already shipped one that a production writer
bypassed by design."* So the refusal is a trigger, and it fires for every door:
`save()`, `QuerySet.update()`, a data migration, an admin form, `psql`.

  * `parent_id`, `task_type` — FROZEN. A unit is never re-parented and never
    re-typed: the accumulate primitive reads both without a lock, and a unit
    moved or re-typed would retroactively change what every event already
    settled on it means.
  * `status` — RESOLVE_ONCE. `active` is the one unresolved value. A unit
    leaves it once, for one terminal state, and that state never moves — the
    five are told apart by who wrote them, and a Charge keys on `completed`.
  * `outcome_reason`, `reason_detail` — SET_ONCE. The caller's reason and its
    sentence are written by the write that ends the work, from nothing (`""`
    is the column's *nobody gave one*), and never again. A stop UBB applied
    leaves both `""` for good, because UBB's own reasons live under the other
    concept, in `metadata`.

**WHY THE KERNEL'S EXISTING GUARDS DO NOT DISCHARGE IT.** `TaskService._flip`
refuses a second transition and the cascade selects only running work, so no
path in the tree rewrites these columns — and that is exactly the kind of
guard ADR-0007 §2 says is not enforcement, because the writers it cannot see
are the ones nobody is watching. `Task.save`'s refusal of a changed kind stays
as the friendly error; this is the rule beneath it.

**Why `BEFORE UPDATE`, and why an insert pays nothing.** Same argument as
`work/0021` one table over: a `CHECK` sees one row and cannot see `OLD`, so it
cannot tell a birth from a change. Registering work — which this rule exists to
leave free — never enters it. The containment rule `0022` installed on this
table is `BEFORE INSERT` and holds who may be born; this one holds what may
happen after, and the two never fire on the same statement.

**The `WHEN` clause is load-bearing rather than an optimisation.** It names all
five columns, so the hot writes on this table — every recording adds to a
unit's totals and stamps its heartbeat, and the announcement is stamped after
the flip — never enter the function. A full-row save re-sending unchanged
values is not a change either (`IS DISTINCT FROM`), which keeps the admin form
and a `save()` without `update_fields` working.

**The refusal is SQLSTATE 23000**, `integrity_constraint_violation`, which
Django raises as `IntegrityError` — the same exception this table's uniqueness
key and containment rule already raise. Each message opens with the column and
its class (`status is declared resolve_once`), and every test asserts that
opening rather than merely that something refused, because this table now
carries two rules and a uniqueness key.

**THE REVERSE IS EXACT**: drop the rule. Nothing was moved; no row is
rewritten.
"""

from django.db import migrations

TRIGGER = "trg_task_declared_transitions"
FUNCTION = "ubb_task_declared_transitions"

#: The one non-terminal Task state, spelled here because a migration must not
#: import application code. The work app's test for this rule holds it to the
#: registry's `TASK_STATUS_ACTIVE`.
UNRESOLVED_STATUS = "active"

#: The five refusals, one block per declared column — a constant of its own
#: because `0029` widens this rule and builds its function from these blocks
#: plus its own, so the two migrations cannot spell one refusal two ways.
REFUSALS = f"""
    IF NEW.parent_id IS DISTINCT FROM OLD.parent_id THEN
        RAISE EXCEPTION
            'parent_id is declared frozen (ADR-0007 §2): a unit of work is '
            'never re-parented, because everything it spent already rolled up '
            'into the work containing it. Got % to %',
            OLD.parent_id, NEW.parent_id
            USING ERRCODE = '23000';
    END IF;

    IF NEW.task_type IS DISTINCT FROM OLD.task_type THEN
        RAISE EXCEPTION
            'task_type is declared frozen (ADR-0007 §2): the kind of work a '
            'unit is decides what every event already settled on it means. '
            'Got % to %',
            OLD.task_type, NEW.task_type
            USING ERRCODE = '23000';
    END IF;

    IF NEW.status IS DISTINCT FROM OLD.status
            AND OLD.status <> '{UNRESOLVED_STATUS}' THEN
        RAISE EXCEPTION
            'status is declared resolve_once (ADR-0007 §2): a unit of work '
            'leaves `{UNRESOLVED_STATUS}` once, for one terminal state, and '
            'that state never moves. Got % to %',
            OLD.status, NEW.status
            USING ERRCODE = '23000';
    END IF;

    -- The caller's explanation is written by the write that ENDS the work,
    -- from nothing, and by no other.
    IF NEW.outcome_reason IS DISTINCT FROM OLD.outcome_reason
            AND NOT (OLD.outcome_reason = ''
                     AND OLD.status = '{UNRESOLVED_STATUS}'
                     AND NEW.status <> '{UNRESOLVED_STATUS}') THEN
        RAISE EXCEPTION
            'outcome_reason is declared set_once (ADR-0007 §2): the caller''s '
            'reason is written by the write that ends the work and never '
            'again. Got % to % (status % to %)',
            OLD.outcome_reason, NEW.outcome_reason, OLD.status, NEW.status
            USING ERRCODE = '23000';
    END IF;

    IF NEW.reason_detail IS DISTINCT FROM OLD.reason_detail
            AND NOT (OLD.reason_detail = ''
                     AND OLD.status = '{UNRESOLVED_STATUS}'
                     AND NEW.status <> '{UNRESOLVED_STATUS}') THEN
        RAISE EXCEPTION
            'reason_detail is declared set_once (ADR-0007 §2): the sentence '
            'beside the caller''s reason is written by the write that ends the '
            'work and never again. Got % to % (status % to %)',
            OLD.reason_detail, NEW.reason_detail, OLD.status, NEW.status
            USING ERRCODE = '23000';
    END IF;
"""

INSTALL = f"""
CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN{REFUSALS}
    RETURN NEW;
END;
$$;

CREATE TRIGGER {TRIGGER}
BEFORE UPDATE ON ubb_task
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status
      OR OLD.parent_id IS DISTINCT FROM NEW.parent_id
      OR OLD.task_type IS DISTINCT FROM NEW.task_type
      OR OLD.outcome_reason IS DISTINCT FROM NEW.outcome_reason
      OR OLD.reason_detail IS DISTINCT FROM NEW.reason_detail)
EXECUTE FUNCTION {FUNCTION}();
"""

UNINSTALL = f"""
DROP TRIGGER {TRIGGER} ON ubb_task;
DROP FUNCTION {FUNCTION}();
"""


def install(apps, schema_editor):
    schema_editor.execute(INSTALL, params=None)


def uninstall(apps, schema_editor):
    schema_editor.execute(UNINSTALL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0027_a_stopped_unit_records_the_control_that_fired'),
    ]

    operations = [
        migrations.RunPython(install, uninstall),
    ]
