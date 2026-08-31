"""A unit of work snapshots HOW IT IS SOLD and, where that is one agreed price,
WHAT that price is — both at start, and neither ever moves (#415, spec §9).

Two columns and one rule.

**`pricing_mode` IS A COPY, AND THAT IS WHY THE DECLARATION NEEDED NO PUBLISH
RECORD.** `TaskType.pricing_mode` is frozen (`0021`) on an argument that leans
directly on this column: nothing in flight or historical can have its revenue
shape change, because the answer is written onto the unit of work the instant it
starts. Without this column that argument is not available and the frozen
declaration would be the only record of a regime, which is what a publish record
would have had to supply. It is NOT NULL with the declaration's own default for
the declaration's own reason — every unit of work registered before this column
existed was registered when per-event was the only regime there was, and a
nullable column would invent a third state for a question every existing row has
already answered.

**`agreed_price_micros` IS THE DETERMINATION, NOT THE CHARGE.** It says WHICH
price applies to this unit of work; whether it is owed at all is decided by how
the work ends, and the canonical record of a charge that really arose is a
different record with a different lifetime (#416). A unit of work that fails
carries this number and is charged nothing. It is pinned at start so that a unit
of work spanning a reprice keeps the number it was quoted, while its supplier
costs float and resolve at each posting's own timestamp — *the price was
promised, the cost is observed.*

**THE RULE COMPARES TWO ROWS, WHICH IS WHY IT IS A TRIGGER AND NOT A CHECK
(#151 §18, spec §9).** Contained work and the unit that contains it must be sold
the same way. A mixed tree produces a number nobody can explain: the parent's
rollup is unconditional, so a per-event child under an agreed-price parent adds
metered revenue to a unit of work whose revenue was supposed to be replaced by
one number, and an agreed-price child under a per-event parent puts revenue at a
level nothing reports at. A `CHECK` is evaluated against ONE row and cannot see
the parent at all, so the invariant is not expressible as a column constraint —
which #151 §18 records as *"the weakest enforcement in the document, and it
guards a money-shaped rule"*. A `BEFORE INSERT ... FOR EACH ROW` trigger can
read the parent, refuses before the write rather than unwinding one, and holds
through every door: `save()`, `QuerySet.update()`, a data migration, `psql`.

**WHY INSERT AND NOT UPDATE.** This is a rule about who may be BORN, which is
exactly the shape `pricing/0020` answers on the rate table and the shape a
`CHECK` cannot take. A unit of work is never re-parented and its regime is never
rewritten — `Task.parent` and the pinned facts beside it say so in prose, under
the model-wide gap `Task.outcome_reason` records — so there is no second
statement for this rule to have an opinion about. Declaring `Task`'s columns
into mutability classes is a separate piece of work with its own migration, and
this trigger does not discharge it: it is a cross-row birth rule, not a
transition class, and it is declared into none.

**IT REFUSES ONLY WHAT IT CAN SEE.** Django creates every foreign key on
PostgreSQL as `DEFERRABLE INITIALLY DEFERRED`, so a `parent_id` naming no row at
all is the FK's business at commit and not this rule's. Reporting *the regimes
disagree* for a parent that does not exist would attribute a referential fault to
a pricing rule, so a missing parent leaves this trigger silent.

**The refusal is raised as SQLSTATE 23000**, `integrity_constraint_violation`,
the class Django maps to `IntegrityError` — the same exception this table's
uniqueness key already raises, because a caller has no business caring which
mechanism held the line. The message names both regimes, and every test of it
asserts them rather than merely that something refused: a table with two
mechanisms on it makes *"something refused this"* stop being evidence.

**THE TWO CHECKS ARE ONE-DIRECTIONAL AND SAY SO.** *A price implies a whole
unit of work sold that way* is a property of one row and a check holds it. The
converse — *every whole fixed unit of work carries a price* — is not expressible
against one row and is not true either, because contained work under an
agreed-price parent is `fixed` too and carries no price of its own. What makes a
whole one carry a price is the start gate refusing to register it otherwise.

**THE REVERSE IS EXACT**: drop the rule, drop the two checks, drop the two
columns. Nothing is unpicked because nothing was moved.
"""

from django.db import migrations, models

TRIGGER = "trg_task_containment_shares_the_pricing_regime"
FUNCTION = "ubb_task_containment_shares_the_pricing_regime"

INSTALL = f"""
CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    containing_regime text;
BEGIN
    SELECT pricing_mode INTO containing_regime
    FROM ubb_task WHERE id = NEW.parent_id;

    -- The parent is not on disk yet, so its regime is not a fact this rule
    -- can read. A foreign key that names no row is the deferred constraint's
    -- refusal at commit, and answering it here would attribute a referential
    -- fault to a pricing rule.
    IF NOT FOUND THEN
        RETURN NEW;
    END IF;

    -- Contained work is sold the way the work containing it is sold. A mixed
    -- tree produces a number nobody can explain: the rollup is unconditional,
    -- so metered revenue underneath an agreed price is added to a unit of work
    -- whose revenue that price was supposed to replace.
    IF containing_regime IS DISTINCT FROM NEW.pricing_mode THEN
        RAISE EXCEPTION
            'pricing_mode must match the unit of work containing this one: '
            'the containing unit is sold %, this one declares % — a mixed '
            'tree produces a number nobody can explain',
            containing_regime, NEW.pricing_mode
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER {TRIGGER}
BEFORE INSERT ON ubb_task
FOR EACH ROW
WHEN (NEW.parent_id IS NOT NULL)
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
        ('customers', '0014_customer_suspension_reason'),
        ('tenants', '0025_the_two_expiry_windows_get_a_tenant_rung'),
        ('work', '0021_a_kind_of_work_declares_how_it_is_sold'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='agreed_price_micros',
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='task',
            name='pricing_mode',
            field=models.CharField(
                choices=[('event_priced', 'Event priced'), ('fixed', 'Fixed price')],
                default='event_priced', max_length=16),
        ),
        migrations.AddConstraint(
            model_name='task',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ('agreed_price_micros__isnull', True),
                    models.Q(('parent__isnull', True), ('pricing_mode', 'fixed')),
                    _connector='OR'),
                name='ck_task_agreed_price_only_on_a_whole_fixed_unit'),
        ),
        migrations.AddConstraint(
            model_name='task',
            constraint=models.CheckConstraint(
                condition=models.Q(('agreed_price_micros__isnull', True),
                                   ('agreed_price_micros__gte', 0),
                                   _connector='OR'),
                name='ck_task_agreed_price_not_negative'),
        ),
        migrations.RunPython(install, uninstall),
    ]
