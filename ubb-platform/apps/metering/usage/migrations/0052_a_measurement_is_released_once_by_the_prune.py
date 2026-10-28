"""A measurement is released once, by the prune, and the table holds it (W5).

**THE RELEASE FACT.** The daily prune (`usage/pruning.py`) removes measurement
records older than the measurement horizon. Each one it removes it first
RELEASES — writes `prunable_at`, the moment the release happened — and then
deletes, inside one transaction, so the `0041` delete rule (a measurement may go
only at or after its `prunable_at`) is satisfied by a fact rather than by a
deadline. W5 ruling 8: `prunable_at` is a SET_ONCE release marker written by the
prune, never a frozen retention deadline stamped at recording.

One rule over one column, held by a trigger for every door — `save()`,
`QuerySet.update()`, a data migration, `psql` — because ADR-0007 §2 says a
model-level guard is not enforcement:

  * `prunable_at` — SET_ONCE. NULL to an instant, once; never moved, never
    withdrawn back to NULL.
  * And the instant is a moment that has COME: a release names when a record
    was let go, so one in the future would be a deadline in disguise, which is
    exactly what the ruling says this column is not. `now()` is the
    transaction's own instant — the prune stamps the release with it, so the
    two read the same clock.

**Why `BEFORE UPDATE` with a `WHEN`.** A measurement is inserted once with its
posting and never updated otherwise (the record's own rule), so the only write
this trigger ever sees is the release; the `WHEN` keeps every other update — a
fixture, an admin — from entering it at all. An insert pays nothing.

**AND THE INDEX THE PRUNE'S QUERY WALKS.** The prune selects the oldest
releasable rows in `(recorded_at, id)` order under a `recorded_at < horizon`
bound, a batch at a time. `ix_measurement_recorded_at` serves that range and
that order, so each batch is an index range scan with no sort, and the backlog
and skipped-count reads walk the same range (the query plan is recorded on the
W5 hand-forward on #190).

**The reverse is real.** Dropping the trigger, its function and the index
returns the table to what `0041` left; this migration moves no row.
"""
from django.db import migrations, models

TRIGGER = "trg_posting_measurement_released_once"
FUNCTION = "ubb_posting_measurement_released_once"

REFUSALS = """
    IF OLD.prunable_at IS NOT NULL THEN
        RAISE EXCEPTION
            'prunable_at is declared set_once (ADR-0007 §2): a measurement is '
            'released once, and its release is never moved or withdrawn. '
            'Got % to %',
            OLD.prunable_at, NEW.prunable_at
            USING ERRCODE = '23000';
    END IF;

    IF NEW.prunable_at > now() THEN
        RAISE EXCEPTION
            'prunable_at is declared set_once (ADR-0007 §2): it records when a '
            'measurement was released, so it cannot name a moment still to '
            'come. Got % at %',
            NEW.prunable_at, now()
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
BEFORE UPDATE ON ubb_posting_measurement
FOR EACH ROW
WHEN (OLD.prunable_at IS DISTINCT FROM NEW.prunable_at)
EXECUTE FUNCTION {FUNCTION}();
"""

UNINSTALL = f"""
DROP TRIGGER {TRIGGER} ON ubb_posting_measurement;
DROP FUNCTION {FUNCTION}();
"""


def install(apps, schema_editor):
    schema_editor.execute(INSTALL, params=None)


def uninstall(apps, schema_editor):
    schema_editor.execute(UNINSTALL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ("usage", "0051_a_posting_is_usd_only"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="postingmeasurement",
            index=models.Index(fields=["recorded_at", "id"],
                               name="ix_measurement_recorded_at"),
        ),
        migrations.RunPython(install, uninstall),
    ]
