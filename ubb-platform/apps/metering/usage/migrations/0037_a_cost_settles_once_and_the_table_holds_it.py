"""The posting table starts refusing every move but the settlement (#318).

#317 put the three legal combinations of amount, status and reason into a
`CHECK`. A `CHECK` is evaluated against **one row**: it can say whether the row
in front of it is legal, and it cannot say whether the row it replaced was. That
is exactly the difference ADR-0007 §2 draws between the two things this column
must tell apart — *"resolution completes previously unknown information;
correction changes a value that was already asserted"* — so today, completing a
blank and changing an answer are indistinguishable at the database.

**The `OLD → NEW` rules are carried by a trigger, and the alternatives were not
dismissed for taste.** A `CHECK` cannot see `OLD` at all. A Postgres `RULE`
rewrites the statement rather than judging it, is documented by its own project
as a sharp edge around `NEW`/`OLD` multiple-evaluation, and would put the
condition somewhere no reader of this table would look. A `BEFORE UPDATE ... FOR
EACH ROW` trigger is the only mechanism that sees both rows, fires for every
door — `save()`, `QuerySet.update()`, a data migration, `psql` — and refuses
before the write rather than unwinding one.

**And the cost was measured rather than assumed**, because ADR-0007's
Consequences require it of this decision specifically and this is the hottest
write path in the system. The fixture, the method and the numbers are in
`scripts/measure_posting_transition_cost.py` and in the acceptance record for
#318. The short version: the trigger is `BEFORE UPDATE` only, so **inserts pay
nothing at all** — the recording path is untouched — and the `WHEN` clause below
means an update that leaves all four columns alone never enters the function
body either. What pays is a settlement, which happens once per posting.

**Why there is no vendor guard, when the neighbouring raw-SQL migrations all
have one.** `0011` and `0022` guard on `connection.vendor` because a GIN index
is an optimisation: a backend without one still holds the data correctly. This
is not an optimisation — it is the enforcement half of a declaration the model
now makes, and a guard would encode a fallback in which the promise is made and
nothing keeps it. That is the precise state
`apps/platform/tests/test_transition_class_declarations.py` exists to refuse. The
table is Postgres-only in any case: two of its indexes are `GinIndex`, and it
carries a `JSONB` containment index that no other backend can build.

**The tokens below are literals, and the model's are not.** `known` and
`unresolved` are frozen into the function body for the reason `0036` gives at
length: a migration records the schema as it was on the day it ran, and
importing living constants into a frozen file makes replay depend on today's
registry. What keeps the copy honest is not this file but a test —
`test_a_cost_settles_once.py::test_the_rule_names_the_status_values_the_registry_declares`
reads the installed function's source out of `pg_proc` and compares it against
`core.vocabulary`, so a rename in `domain-vocabulary/` turns red here rather
than leaving a rule that quietly matches nothing.

**The refusal is raised as SQLSTATE 23000**, `integrity_constraint_violation`,
which is the class Django maps to `IntegrityError` — the same exception the
`CHECK` constraints beside it raise, because a caller has no business caring
which mechanism held the line. The *message* distinguishes them: this one names
the transition class it is enforcing, and a `CHECK` names its own constraint.

**The reverse is real and it is total.** Dropping the trigger and its function
returns the table to what `0036` left, which is a table whose combinations are
still checked and whose history is not. Nothing has to be unpicked because
nothing was written: this migration adds no column and moves no row.
"""

from django.db import migrations

TRIGGER = "trg_posting_declared_transitions"
FUNCTION = "ubb_posting_declared_transitions"

INSTALL = f"""
CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- claimed_provider_cost_micros is declared FROZEN: what the caller said is
    -- a record of what was said, so it takes no value after insert and changes
    -- none.
    IF NEW.claimed_provider_cost_micros
       IS DISTINCT FROM OLD.claimed_provider_cost_micros THEN
        RAISE EXCEPTION
            'claimed_provider_cost_micros is declared frozen (ADR-0007 §2): '
            'a claim is a record of what was said at the time'
            USING ERRCODE = '23000';
    END IF;

    -- provider_cost_micros and costing_status are declared RESOLVE_ONCE AS A
    -- PAIR, and unresolved_reason moves with them: the one permitted statement
    -- sets the amount, moves the status to known and clears the reason at once.
    IF NEW.provider_cost_micros IS DISTINCT FROM OLD.provider_cost_micros
       OR NEW.costing_status IS DISTINCT FROM OLD.costing_status
       OR NEW.unresolved_reason IS DISTINCT FROM OLD.unresolved_reason THEN
        IF OLD.costing_status <> 'unresolved'
           OR OLD.provider_cost_micros IS NOT NULL
           OR NEW.costing_status <> 'known'
           OR NEW.provider_cost_micros IS NULL
           OR NEW.unresolved_reason IS NOT NULL THEN
            RAISE EXCEPTION
                'provider_cost_micros and costing_status are declared '
                'resolve_once (ADR-0007 §2): the only permitted move is '
                'unresolved to known, settling the amount and clearing the '
                'reason in one statement; got % to %',
                OLD.costing_status, NEW.costing_status
                USING ERRCODE = '23000';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER {TRIGGER}
BEFORE UPDATE ON ubb_posting
FOR EACH ROW
WHEN (OLD.provider_cost_micros IS DISTINCT FROM NEW.provider_cost_micros
      OR OLD.costing_status IS DISTINCT FROM NEW.costing_status
      OR OLD.unresolved_reason IS DISTINCT FROM NEW.unresolved_reason
      OR OLD.claimed_provider_cost_micros
         IS DISTINCT FROM NEW.claimed_provider_cost_micros)
EXECUTE FUNCTION {FUNCTION}();
"""

UNINSTALL = f"""
DROP TRIGGER {TRIGGER} ON ubb_posting;
DROP FUNCTION {FUNCTION}();
"""


def install(apps, schema_editor):
    schema_editor.execute(INSTALL, params=None)


def uninstall(apps, schema_editor):
    schema_editor.execute(UNINSTALL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ("usage", "0036_a_cost_ubb_does_not_know_stops_being_zero"),
    ]

    operations = [
        migrations.RunPython(install, uninstall),
    ]
