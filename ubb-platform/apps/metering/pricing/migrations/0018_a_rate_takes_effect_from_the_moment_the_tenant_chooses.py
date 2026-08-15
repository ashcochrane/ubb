"""A rate's effective moment becomes the caller's, and then stops moving (#325).

Two operations, and they belong in one migration because the second is what
makes the first safe. `AlterField` takes `auto_now_add=True` off `valid_from`,
which is the whole of the defect: that flag does not default, it **overwrites
whatever the caller supplied on every insert**, so a tenant could only ever
declare a rule effective from the instant the row was written. The trigger then
declares what may happen to the two columns resolution reads afterwards.

**Dropping the flag alone would have been a different defect.** ADR-0007 §2
requires mutability declared per field *and* enforced by the database; a column
that merely stopped being auto-stamped would be a column anything could move.
The model states the two classes in `transition_classes` and this file is what
keeps them:

* `valid_from` — **frozen**. When a rule took effect is a fact about the rule.
  Moving it retroactively re-costs work that has already reported.
* `valid_to` — **set_once**. Closing a rule is a one-way act; reopening one over
  a period that has already reported is a rewrite of history, not an edit.

**One rule over both halves of the table, because there is only one table.**
`ubb_rate_card` carries the cost side and the price side, discriminated by a
column, and a rule that held only one of them would hold neither in any way a
reader could rely on. The trigger never consults that discriminator.

**Why a trigger, and why `BEFORE UPDATE`.** A `CHECK` is evaluated against one
row and cannot see `OLD` at all, so it cannot tell filling a blank from
replacing an answer — which is the entire difference between `set_once` and a
correction. A Postgres `RULE` rewrites the statement rather than judging it. A
`BEFORE UPDATE ... FOR EACH ROW` trigger sees both rows, fires for every door —
`save()`, `QuerySet.update()`, a data migration, `psql` — and refuses before the
write rather than unwinding one. `0037` on the posting table is the same
mechanism for the same reason and argues it at length.

**Inserts pay nothing, which is what makes this free on the path that matters.**
The trigger is `BEFORE UPDATE` only, so declaring a rate — the statement this
ticket exists to permit — never enters it. The `WHEN` clause means an update
leaving both columns alone does not either, and that is every write this table
takes on the recording path: rates are read there, never written. What pays is a
retirement or a reprice, which happens when a human changes a price.

**No vendor guard, on the same ground `0037` states it.** This is the
enforcement half of a declaration the model now makes, not an optimisation, and
a guard would encode a fallback in which the promise is made and nothing keeps
it — precisely the state
`apps/platform/tests/test_transition_class_declarations.py` exists to refuse.

**The refusal is raised as SQLSTATE 23000**, `integrity_constraint_violation`,
the class Django maps to `IntegrityError` — the same exception this table's
existing partial unique index raises, because a caller has no business caring
which mechanism held the line. The *message* distinguishes them: this one names
the transition class it is enforcing, and every test of it asserts that name
rather than merely that something refused.

**The reverse is real, and a test runs it both ways.** Dropping the trigger and
its function returns the table to what `0017` left. Nothing has to be unpicked
because nothing was written: this migration adds no column and moves no row.
"""

import django.utils.timezone
from django.db import migrations, models

TRIGGER = "trg_rate_declared_transitions"
FUNCTION = "ubb_rate_declared_transitions"

INSTALL = f"""
CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- valid_from is declared FROZEN: a rule's effective moment is a fact about
    -- the rule, and moving it re-costs work that has already reported.
    IF NEW.valid_from IS DISTINCT FROM OLD.valid_from THEN
        RAISE EXCEPTION
            'valid_from is declared frozen (ADR-0007 §2): when a rate took '
            'effect is a fact about the rate, and moving it re-costs work '
            'that has already reported; got % to %',
            OLD.valid_from, NEW.valid_from
            USING ERRCODE = '23000';
    END IF;

    -- valid_to is declared SET_ONCE: nothing to a moment, once. Opening the
    -- close again, or moving it, both land here; leaving it alone does not
    -- reach the function at all.
    IF NEW.valid_to IS DISTINCT FROM OLD.valid_to
       AND OLD.valid_to IS NOT NULL THEN
        RAISE EXCEPTION
            'valid_to is declared set_once (ADR-0007 §2): closing a rate is a '
            'one-way act, and reopening one over a period that has already '
            'reported rewrites history rather than editing it; got % to %',
            OLD.valid_to, NEW.valid_to
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER {TRIGGER}
BEFORE UPDATE ON ubb_rate_card
FOR EACH ROW
WHEN (OLD.valid_from IS DISTINCT FROM NEW.valid_from
      OR OLD.valid_to IS DISTINCT FROM NEW.valid_to)
EXECUTE FUNCTION {FUNCTION}();
"""

UNINSTALL = f"""
DROP TRIGGER {TRIGGER} ON ubb_rate_card;
DROP FUNCTION {FUNCTION}();
"""


def install(apps, schema_editor):
    schema_editor.execute(INSTALL, params=None)


def uninstall(apps, schema_editor):
    schema_editor.execute(UNINSTALL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0017_ten_slots_on_the_rate'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rate',
            name='valid_from',
            field=models.DateTimeField(db_index=True, default=django.utils.timezone.now),
        ),
        migrations.RunPython(install, uninstall),
    ]
