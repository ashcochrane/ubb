"""A delivered piece of work sold at one agreed price is charged once, and the
record of it can never be rewritten (#416, spec §11).

One table and one rule. Until now the only thing a delivered piece of work sold
that way produced was the DETERMINATION pinned on its own row — which price
applies — and #415 said in its own message that a charge did not follow. This
is the charge.

**WHY THE PINNED PRICE COULD NOT BE THIS RECORD**, stated here because the
column and the table now sit one app apart and a reader will ask. Three reasons,
and each is a column of this table: a unit of work's row is MUTABLE and this one
is not; a unit of work carries NO CURRENCY at all, while a movement of money is
a fact about one; and a determination must be able to exist and never become a
charge, which is every ending but delivery and is ordinary. One-to-zero-or-one,
different lifetimes.

**AND WHY NOT A SYSTEM-GENERATED POSTING**, which was the cheaper answer and was
rejected. It would have bought every money path for free, but a posting is
immutable AND undeletable — so a wrong projection could never be corrected, and
would be permanent by construction. #417 makes the posting a PROJECTION of this
row instead, which is what makes a wrong one rebuildable from a right one.

**THE RULE IS THE ENFORCEMENT HALF OF A DECLARATION THE MODEL MAKES.**
`Charge.transition_classes` declares every economic column `FROZEN` — ADR-0007
§2's *none after insert* — and that ADR is explicit that a model-level guard
alone is not enforcement: *"the repository has already shipped one that a
production writer bypassed by design."* So the refusal is a trigger, and it
fires for every door: `save()`, `QuerySet.update()`, a data migration, `psql`.
Corrections are compensating records — another row of this table naming the one
it corrects — never edits, so a wrong charge leaves a trail rather than being
rewritten.

**THE RULE NAMES THE COLUMNS THAT MOVED, NOT MERELY THAT SOMETHING DID.** A
message reading *this record is frozen* would be satisfiable by any of nineteen
columns and would leave every assertion about it unable to discriminate — which
is #352's lesson exactly, paid for on a table that acquired a second rule. The
body diffs `to_jsonb(OLD)` against `to_jsonb(NEW)` over a named set, so the
exception carries the offending columns and the set is load-bearing rather than
decorative: deleting a name from it stops that column being defended, and G19
then reports it undefended.

**WHY NO `WHEN` CLAUSE**, which `work/0021` and `pricing/0018` both carry. Those
guard ONE scalar on a table an idempotent PUT rewrites in full, where a rule
firing on equal values would refuse a caller re-sending what it already sent.
Nothing updates this table at all — a correction is an INSERT — so there is no
re-send to admit and no hot path to keep out of. A nineteen-column `WHEN` would
restate the function's own condition in a second place where the two could
disagree.

**The refusal is raised as SQLSTATE 23000**, `integrity_constraint_violation`,
the class Django maps to `IntegrityError` — the same exception this table's two
uniqueness keys already raise, because a caller has no business caring which
mechanism held the line.

**THE REVERSE IS EXACT**: drop the rule, drop the table. Nothing else is
touched, because nothing else was.
"""
import uuid

import django.db.models.deletion
from django.db import migrations, models

TRIGGER = "trg_charge_declared_transitions"
FUNCTION = "ubb_charge_declared_transitions"

#: EVERY COLUMN `Charge.transition_classes` DECLARES `FROZEN`, spelled once so
#: the rule and the declaration cannot drift apart in silence. `correction_note`
#: and `updated_at` are deliberately absent: the first is display text beside a
#: correction rather than an economic fact, and the second is bookkeeping.
FROZEN_COLUMNS = (
    "task_id",
    "amount_micros",
    "currency",
    "agreed_price_line_id",
    "book_version",
    "resolved_at",
    "charged_at",
    "idempotency_key",
    "compensates_id",
    "grouping_field_1",
    "grouping_field_2",
    "grouping_field_3",
    "grouping_field_4",
    "grouping_field_5",
    "grouping_field_6",
    "grouping_field_7",
    "grouping_field_8",
    "grouping_field_9",
    "grouping_field_10",
)

_FROZEN_SQL_ARRAY = ", ".join(f"'{column}'" for column in FROZEN_COLUMNS)

INSTALL = f"""
CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    moved text[];
BEGIN
    -- Every economic column of a Charge is declared FROZEN: what UBB charged a
    -- customer, in which currency, against which line of which version of which
    -- book, and at which instants, are facts about a money movement that
    -- already happened. Correcting one is another row of this table naming it,
    -- never a rewrite of it.
    SELECT array_agg(changed.key ORDER BY changed.key) INTO moved
    FROM (
        SELECT after.key
        FROM jsonb_each(to_jsonb(NEW)) AS after(key, value)
        JOIN jsonb_each(to_jsonb(OLD)) AS before(key, value)
          ON before.key = after.key
        WHERE after.value IS DISTINCT FROM before.value
          AND after.key = ANY (ARRAY[{_FROZEN_SQL_ARRAY}])
    ) AS changed;

    IF moved IS NOT NULL THEN
        RAISE EXCEPTION
            'these columns of ubb_charge are declared frozen (ADR-0007 2): '
            '%. A charge records money that already moved; correct it with a '
            'compensating record naming it, which leaves a trail, rather than '
            'by rewriting what it says.',
            array_to_string(moved, ', ')
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER {TRIGGER}
BEFORE UPDATE ON ubb_charge
FOR EACH ROW
EXECUTE FUNCTION {FUNCTION}();
"""

UNINSTALL = f"""
DROP TRIGGER {TRIGGER} ON ubb_charge;
DROP FUNCTION {FUNCTION}();
"""


def install(apps, schema_editor):
    schema_editor.execute(INSTALL, params=None)


def uninstall(apps, schema_editor):
    schema_editor.execute(UNINSTALL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0030_a_book_holds_one_agreed_price_for_a_kind_of_work'),
        ('tenants', '0025_the_two_expiry_windows_get_a_tenant_rung'),
        ('work', '0023_the_version_of_the_book_that_answered_is_pinned_too'),
    ]

    operations = [
        migrations.CreateModel(
            name='Charge',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('amount_micros', models.BigIntegerField()),
                ('currency', models.CharField(max_length=3)),
                ('agreed_price_line_id', models.UUIDField()),
                ('book_version', models.PositiveIntegerField()),
                ('resolved_at', models.DateTimeField()),
                ('charged_at', models.DateTimeField()),
                ('idempotency_key', models.CharField(max_length=128)),
                ('correction_note', models.TextField(blank=True, default='')),
                ('grouping_field_1', models.CharField(blank=True, default='', max_length=100)),
                ('grouping_field_2', models.CharField(blank=True, default='', max_length=100)),
                ('grouping_field_3', models.CharField(blank=True, default='', max_length=100)),
                ('grouping_field_4', models.CharField(blank=True, default='', max_length=100)),
                ('grouping_field_5', models.CharField(blank=True, default='', max_length=100)),
                ('grouping_field_6', models.CharField(blank=True, default='', max_length=100)),
                ('grouping_field_7', models.CharField(blank=True, default='', max_length=100)),
                ('grouping_field_8', models.CharField(blank=True, default='', max_length=100)),
                ('grouping_field_9', models.CharField(blank=True, default='', max_length=100)),
                ('grouping_field_10', models.CharField(blank=True, default='', max_length=100)),
                ('compensates', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='compensations', to='pricing.charge')),
                ('task', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='charges', to='work.task')),
                ('tenant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='charges', to='tenants.tenant')),
            ],
            options={
                'db_table': 'ubb_charge',
                'indexes': [models.Index(fields=['tenant', 'charged_at'],
                                         name='idx_charge_tenant_charged')],
                'constraints': [
                    models.UniqueConstraint(
                        condition=models.Q(('compensates__isnull', True)),
                        fields=('task',),
                        name='uq_charge_one_original_per_unit_of_work'),
                    models.UniqueConstraint(
                        fields=('tenant', 'idempotency_key'),
                        name='uq_charge_idempotency_key'),
                    models.CheckConstraint(
                        condition=models.Q(('compensates__isnull', False),
                                           ('amount_micros__gte', 0),
                                           _connector='OR'),
                        name='ck_charge_an_original_is_not_negative'),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(('compensates__isnull', True),
                                     ('correction_note', '')),
                            models.Q(('compensates__isnull', False),
                                     models.Q(('correction_note', ''),
                                              _negated=True)),
                            _connector='OR'),
                        name='ck_charge_a_correction_says_why'),
                ],
            },
        ),
        migrations.RunPython(install, uninstall),
    ]
