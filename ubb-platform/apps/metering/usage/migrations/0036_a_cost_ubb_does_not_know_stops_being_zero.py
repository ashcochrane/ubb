"""A supplier cost UBB has not learned yet stops being recorded as zero (#317).

`provider_cost_micros` was `BigIntegerField(default=0)` and there was no value in
it meaning *not resolved*. A supplier charge nobody had told UBB about was
therefore stored as the same number as a call that genuinely cost nothing, and
every total built on the column was wrong in the direction that looks healthy.
This migration makes the column nullable, gives it the status that says which
reading applies, and puts the rule between them in the table rather than in the
application.

**WHAT HAPPENS TO THE ROWS THAT ALREADY EXIST: EVERY ONE TAKES `known`.** No
source document rules on this, so the ruling is recorded here, where a reader of
the history will be standing when they ask.

UBB cannot tell a historical genuine zero from a historical unknown, because the
distinction was never captured — that absence is the defect being fixed, and no
migration can recover information that was never written down. The two available
answers are therefore not symmetric:

* `unresolved` would invent an unknown the system never observed. It would put
  every past period into a partial state, and it would put those rows into a
  status whose only exit is a settlement nobody is in a position to perform:
  there is no supplier statement to reconcile them against and no reason value
  that would be true of them.
* `known` records what UBB actually holds. The number in the column is the
  number the system has always used for these rows, in every total it has ever
  reported; calling it `known` changes no answer and claims nothing new.

So the backfill is a statement about UBB's knowledge, not about the supplier's
invoice, and it is deliberately the reading that leaves history reading exactly
as it did yesterday. The `default` on the added column is what carries it: every
existing row is written `known` as the column arrives, in one statement, and
`AddField` is a data-carrying operation here rather than a schema-only one.

**Nullable is not a data change.** `AlterField` on `provider_cost_micros` drops
a NOT NULL and nothing else. No existing value moves and no row becomes null —
NULL becomes *sayable*, and the first rows to say it are written by the tickets
that follow this one.

**Order.** The column becomes nullable and the three new columns arrive before
any constraint is added, because the combination check names all three and
Postgres validates a `CHECK` against the rows already in the table. Adding it
first would fail against a table whose every row is `known` in fact and empty in
the column.

**The `choices` lists below are literals, and everywhere else they are not.**
`apps/metering/usage/models.py` derives both from the frozensets in
`core.vocabulary`, so no living surface holds a copy that can drift from
`domain-vocabulary/`. A migration is the opposite kind of document: it records
the schema as it was on the day it ran, which is why
`apps/platform/tenants/migrations/0019_two_position_enforcement_mode.py` — in
another app, so look there rather than beside this file — still spells a value
that no longer exists. Importing living constants into a frozen file would make
replay depend on today's registry.
`choices` emits no DDL in any case — the value sets are defended by the two
checks below, not by this argument.

**The reverse is honest rather than total, and the asymmetry is the point.** The
constraints drop, the three columns drop, and the cost column goes back to NOT
NULL — which will refuse to run if any row has by then recorded a cost it does
not know. That is correct: reversing is only safe while nothing has used the
capability, and a reverse that "worked" by writing zeroes over unresolved rows
would recreate the exact falsehood this migration exists to remove, silently and
in bulk. Reverse first, resolve second.
"""

from django.db import migrations, models

#: Frozen copies, for the reason the module docstring gives. The living lists
#: are derived from `core.vocabulary` in the model.
COSTING_STATUS = [
    ("known", "known"),
    ("not_applicable", "not_applicable"),
    ("unresolved", "unresolved"),
]
UNRESOLVED_REASON = [
    ("cost_rate_missing", "cost_rate_missing"),
    ("measurement_not_declared", "measurement_not_declared"),
    ("reported_cost_missing", "reported_cost_missing"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("usage", "0035_ten_slots_and_the_six_per_slot_indexes_dropped"),
    ]

    operations = [
        # 1. NULL becomes sayable. No row moves.
        migrations.AlterField(
            model_name="posting",
            name="provider_cost_micros",
            field=models.BigIntegerField(blank=True, default=0, null=True),
        ),
        # 2. The status, carrying `known` onto every row that already exists.
        migrations.AddField(
            model_name="posting",
            name="costing_status",
            field=models.CharField(choices=COSTING_STATUS, default="known",
                                   max_length=32),
        ),
        # 3. The reason, which only an `unresolved` row may carry.
        migrations.AddField(
            model_name="posting",
            name="unresolved_reason",
            field=models.CharField(blank=True, choices=UNRESOLVED_REASON,
                                   max_length=32, null=True),
        ),
        # 4. The caller's belief, which is never COGS and is never summed.
        migrations.AddField(
            model_name="posting",
            name="claimed_provider_cost_micros",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        # 5-6. The two closed sets, at the database.
        migrations.AddConstraint(
            model_name="posting",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("costing_status__in",
                     ["known", "not_applicable", "unresolved"])),
                name="ck_posting_costing_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="posting",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("unresolved_reason__isnull", True),
                    ("unresolved_reason__in",
                     ["cost_rate_missing", "measurement_not_declared",
                      "reported_cost_missing"]),
                    _connector="OR",
                ),
                name="ck_posting_unresolved_reason",
            ),
        ),
        # 7. The three legal combinations, and there are only three.
        migrations.AddConstraint(
            model_name="posting",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("costing_status", "known"),
                             ("provider_cost_micros__isnull", False),
                             ("unresolved_reason__isnull", True)),
                    models.Q(("costing_status", "unresolved"),
                             ("provider_cost_micros__isnull", True),
                             ("unresolved_reason__isnull", False)),
                    models.Q(("costing_status", "not_applicable"),
                             ("provider_cost_micros__isnull", True),
                             ("unresolved_reason__isnull", True)),
                    _connector="OR",
                ),
                name="ck_posting_costing_status_agrees_with_the_cost",
            ),
        ),
    ]
