"""The posting table learns which kind of posting each row is, and freezes it
(#417, spec §12).

Until now every row on this table was a metered event, because every row was
reported by a caller through the recording route. `apps/metering/usage/
measurements.py` said so in its own docstring and answered `metered_usage` from
one function *"so that the day the column arrives there is one line to change"*.
#416 built the canonical `pricing.Charge`; this is the column that lets its 1:1
projection be told apart from the events beside it.

**WHY A COLUMN AND NOT A FLAG DERIVED FROM THE SHAPE OF THE ROW.** A charge
projection is distinguishable by inspection today — no measurement child, a zero
supplier cost, an empty Event Type — and every one of those is a coincidence
rather than a definition. A metered event whose caller declared no measurements
and whose supplier cost settled at nothing has the same shape and is not a
charge; ADR-0006 §4's rule is that the wrong encoding is always the one nobody
is looking at, and a discriminator inferred from three unrelated columns is
three chances to infer it differently in three readers.

**THE DEFAULT IS `metered_usage` AND IT IS NOT A GUESS.** Every row this table
already holds arrived through the recording route, so the backfill states what
those rows have always been rather than assuming it — it is the same answer the
seam function returned for them, written where the rows are.

**THE VALUE SET IS CHECKED AT THE DATABASE**, which is the shape the four
value-set checks already on this table take, for their reason: a closed concept
that only `clean()` defends is open to everything that writes without
validating, and most of what writes here does.

**AND THE COLUMN IS `FROZEN` — A FOURTH TRIGGER, NOT A FOURTH BRANCH IN AN
EXISTING ONE.** `0039` made the argument for a second rule beside `0037`'s and
`0040` followed it for a third; this is the same argument a fourth time. The
rules govern **disjoint columns**: each `WHEN` clause names only its own, so a
supplier settlement never enters this function and a kind that never moves never
enters any of them. Merged, every write touching any governed column would
evaluate every body. Dropping this rule leaves the other three standing, which
is what makes the reverse below a real reverse.

**WHY `FROZEN` AND NOT `RESOLVE_ONCE`.** The three rules already here each admit
one move, because each governs information that arrives late: a supplier cost
settles, a price UBB could not resolve completes, a receipt section seals. This
column has no late arrival to admit. A row is born a metered event or a charge
projection, by the writer that inserted it, and nothing about the world can make
that answer different afterwards — ADR-0007 §2's *none after insert*.

**WHY INSERT IS NOT GUARDED AND UPDATE IS.** A birth rule would ask *who may
create a `task_charge` row*, and the database cannot answer it: `ubb_posting`
has one caller-facing writer and one system writer and no column says which one
is running. What the database CAN say is that the answer never changes, which is
this rule. Which rows may be BORN a charge is held one layer up, by the
projection being the only code that writes the value — and by
`ck_charge_one_original_per_unit_of_work` and this table's own
`uq_usage_event_idempotency_v2` making a second projection of one Charge an
error rather than a second row.

**THE COST.** `BEFORE UPDATE` only, so **inserts pay nothing at all** — which
matters here more than for the three rules beside it, because this column is on
every row on the hottest insert path in the system and the rule stays out of
it entirely. The `WHEN` clause is one `IS DISTINCT FROM` Postgres evaluates
without calling the function, so an update settling a supplier cost never enters
this body either. No figure is quoted: slices 3 and 4 measured rules whose
`WHEN` clauses fire on the columns a settlement moves, and this one fires on a
column no production statement moves at all, so there is no state to alternate
between and nothing above the noise floor to measure.

**The tokens below are literals, and the model's are not**, for the reason
`0036` and `0039` both give: a migration records the schema as it was on the day
it ran, and importing living constants into a frozen file makes replay depend on
today's registry. What keeps the copy honest is a test rather than this file —
`test_a_postings_kind_is_settled_at_birth.py` reads the installed function's
source out of `pg_proc` and compares it against `core.vocabulary`.

**The refusal is raised as SQLSTATE 23000**, `integrity_constraint_violation`,
the class Django maps to `IntegrityError` — the same exception the `CHECK`
constraints beside it raise, because a caller has no business caring which
mechanism held the line. The message names the transition class and the column.

**The reverse is real and it is total.** Dropping this trigger and its function
returns the table to a schema whose kinds are still checked against the closed
set and whose kind history is not; dropping the column returns it to one where
every row is a metered event, which is what every row on it was.
"""

from django.db import migrations, models

TRIGGER = "trg_posting_kind_frozen"
FUNCTION = "ubb_posting_kind_frozen"

INSTALL = f"""
CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- kind is declared FROZEN: none after insert. There is no permitted move,
    -- so this body has no legal branch to fall through to — a statement that
    -- reaches it has already changed the column, which the WHEN clause below
    -- established, and changing it is the whole of what is refused.
    --
    -- The two values are spelled in the message rather than tested, on
    -- purpose: what is refused is the MOVE and not the destination, so a rule
    -- that named a legal target would be a rule about which conversions are
    -- allowed, and none is.
    RAISE EXCEPTION
        'kind is declared frozen (ADR-0007 §2): a posting is born a '
        'metered_usage event or a task_charge projection and is never '
        'converted; got % to %',
        OLD.kind, NEW.kind
        USING ERRCODE = '23000';
END;
$$;

CREATE TRIGGER {TRIGGER}
BEFORE UPDATE ON ubb_posting
FOR EACH ROW
WHEN (OLD.kind IS DISTINCT FROM NEW.kind)
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
        ("usage", "0043_the_second_correlation_value_is_deleted"),
    ]

    operations = [
        migrations.AddField(
            model_name="posting",
            name="kind",
            field=models.CharField(
                choices=[("metered_usage", "metered_usage"),
                         ("task_charge", "task_charge")],
                default="metered_usage", max_length=32),
        ),
        migrations.AddConstraint(
            model_name="posting",
            constraint=models.CheckConstraint(
                condition=models.Q(kind__in=["metered_usage", "task_charge"]),
                name="ck_posting_kind"),
        ),
        migrations.RunPython(install, uninstall),
    ]
