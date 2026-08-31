"""A kind of work declares how it is SOLD, and that declaration never moves
(#414).

One column and one rule. Every revenue path in UBB is per-event: a tenant who
quotes one agreed price for a delivered piece of work has to reverse-engineer a
per-event rate that happens to sum to that number, which it will not, because
how many events the work takes is not knowable when the price is quoted.
`pricing_mode` is the declaration that makes the other answer sayable —
`event_priced` prices each event as it arrives, `fixed` replaces metered
revenue for the whole delivered piece of work with one agreed number.

**PURE ADDITION AND NO ROW IS REWRITTEN, BUT THE DEFAULT IS A RECORD RATHER
THAN A FILLER.** Every declaration that predates this column was made when
per-event was the only regime there was, so `event_priced` is what those rows
have always meant. The column is NOT NULL for exactly that reason: a nullable
one would invent a third state — *nobody said* — for a question every existing
row has already answered, and the start gate that resolves a price would then
have to guess what a null meant.

**THE RULE IS THE ENFORCEMENT HALF OF A DECLARATION THE MODEL MAKES.**
`TaskType.transition_classes` declares `pricing_mode` FROZEN — ADR-0007 §2's
*none after insert* — and that ADR is explicit that a model-level guard alone
is not enforcement: *"the repository has already shipped one that a production
writer bypassed by design."* So the refusal is a trigger, and it fires for
every door: `save()`, `QuerySet.update()`, a data migration, `psql`.

**Why FROZEN rather than a publish record**, which is the question this column
would otherwise leave open (spec §10). The risk a publish record addresses is
already addressed twice over: the regime is snapshotted onto a unit of work at
start, so nothing in flight or historical can change, and what remains —
FUTURE work of that kind — is answered by retiring the declaration and making
a new one. That leaves two rows, each with its own `retired_at`, which is
exactly the *when did this change, and to what* a publish record exists to
answer. Whether the Pricing Book's publish and the Event Type's draft state are
one mechanism or two is genuinely open (#156 §14.2), and minting a third here
would answer that by shipping rather than by deciding.

**Why `BEFORE UPDATE`, and why an insert pays nothing.** A `CHECK` is evaluated
against one row and cannot see `OLD` at all, so it cannot tell a declaration
from a change to one. A `BEFORE UPDATE ... FOR EACH ROW` trigger sees both
rows, refuses before the write rather than unwinding one, and never enters on
an INSERT — so declaring a kind of work, which is the statement this ticket
exists to permit, costs nothing. `pricing/0018` on the rate table is the same
mechanism for the same reason and argues it at length.

**The `WHEN` clause is load-bearing rather than an optimisation.** The
registry's write surface is an idempotent PUT that writes every column of a
declaration on every call, so a rule that fired on equal values would refuse a
tenant re-sending the declaration it already made.

**The refusal is raised as SQLSTATE 23000**, `integrity_constraint_violation`,
the class Django maps to `IntegrityError` — the same exception this table's
uniqueness key already raises, because a caller has no business caring which
mechanism held the line. The message is what distinguishes them: it names the
COLUMN and the transition class, and every test of it asserts both rather than
merely that something refused.

**THE REVERSE IS EXACT**: drop the rule, drop the column. Nothing has to be
unpicked because nothing was moved — this migration adds a column with a
default and installs a rule, and reversing it returns the table to what `0020`
left.
"""

from django.db import migrations, models

TRIGGER = "trg_task_type_declared_transitions"
FUNCTION = "ubb_task_type_declared_transitions"

INSTALL = f"""
CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- pricing_mode is declared FROZEN: how a kind of work is sold is a fact
    -- about that kind of work, and changing it re-prices everything it does
    -- next against terms nobody quoted. Changing the regime is a retirement
    -- plus a new declaration, which leaves a record of both.
    IF NEW.pricing_mode IS DISTINCT FROM OLD.pricing_mode THEN
        RAISE EXCEPTION
            'pricing_mode is declared frozen (ADR-0007 §2): how a kind of '
            'work is sold is a fact about that kind of work, and changing it '
            're-prices everything it does next; retire this kind of work and '
            'declare a replacement instead. Got % to %',
            OLD.pricing_mode, NEW.pricing_mode
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER {TRIGGER}
BEFORE UPDATE ON ubb_task_type
FOR EACH ROW
WHEN (OLD.pricing_mode IS DISTINCT FROM NEW.pricing_mode)
EXECUTE FUNCTION {FUNCTION}();
"""

UNINSTALL = f"""
DROP TRIGGER {TRIGGER} ON ubb_task_type;
DROP FUNCTION {FUNCTION}();
"""


def install(apps, schema_editor):
    schema_editor.execute(INSTALL, params=None)


def uninstall(apps, schema_editor):
    schema_editor.execute(UNINSTALL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0020_a_kind_of_work_declares_how_long_it_may_run'),
    ]

    operations = [
        migrations.AddField(
            model_name='tasktype',
            name='pricing_mode',
            field=models.CharField(
                choices=[('event_priced', 'Event priced'), ('fixed', 'Fixed price')],
                default='event_priced', max_length=16),
        ),
        migrations.RunPython(install, uninstall),
    ]
