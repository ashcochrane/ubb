"""A customer price UBB could not resolve stops being recorded as zero (#351).

`billed_cost_micros` was `BigIntegerField(default=0)` and there was no value in
it meaning *not resolved*. A charge UBB could not price was therefore stored as
the same number as a call priced at exactly nothing, and a customer who should
have been charged and was not looked identical to one correctly charged nothing
— with no queue of the first kind to work through. This migration makes the
column nullable, gives it the status that says which reading applies, adds the
reason that separates the two causes of `not_applicable`, and puts the rule
between them in the table rather than in the application.

The mirror of `0036_a_cost_ubb_does_not_know_stops_being_zero`, and its
docstring is the argument in full. What follows is only what differs.

**WHAT HAPPENS TO THE ROWS THAT ALREADY EXIST: EVERY ONE TAKES `known`**, for
the reason 0036 records — UBB cannot tell a historical genuine zero from a
historical unresolved price, because the distinction was never captured, and
`known` records what UBB actually holds while `unknown` would invent a gap the
system never observed. The `default` on the added column carries it in one
statement, so `AddField` is data-carrying here rather than schema-only.

**FOUR STATUSES, NOT THREE, AND TWO OF THEM SHARE A SHAPE.** `waived` and
`unknown` both carry a NULL amount and no reason. The combination check below
therefore has four branches where 0036 had three, and the two matching branches
are written out rather than folded together: the rule is about four statuses,
and a disjunction enumerating three would read as though one had been forgotten.

**`not_applicable` is the only status that REQUIRES a reason**, which inverts
0036's arrangement — there `unresolved` required one. That is not an
inconsistency between the two pairs but the difference between them: a supplier
cost that is missing owes the reader an input to chase, while a price that does
not apply owes the reader which of two mutually exclusive causes produced it.
An unknown price has no cause to name; that is what unknown means.

**Order.** The column becomes nullable and the two new columns arrive before any
constraint is added, because the combination check names all three and Postgres
validates a `CHECK` against the rows already in the table.

**No trigger, and no transition class.** The columns land defended by `CHECK`
constraints alone. The `RESOLVE_ONCE`-style rule over them — and the declaration
that names it — is #352's, in one commit, because a column declared into a
database-defended class before the database defends it is what
`apps/platform/tests/test_transition_class_declarations.py` refuses.

**The reverse is honest rather than total**, exactly as 0036's is: the
constraints drop, the two columns drop, and the price column goes back to NOT
NULL, which will refuse to run if any row has by then recorded a price UBB could
not resolve. Reverse first, resolve second.

**The `choices` lists below are literals, and everywhere else they are not** —
0036's paragraph on why a migration is the one document that may hold a frozen
copy applies here unchanged. `choices` emits no DDL in any case; the value sets
are defended by the two checks below.
"""

from django.db import migrations, models

#: Frozen copies, for the reason 0036's module docstring gives. The living lists
#: are derived from `core.vocabulary` in the model.
PRICING_STATUS = [
    ("known", "known"),
    ("not_applicable", "not_applicable"),
    ("unknown", "unknown"),
    ("waived", "waived"),
]
NOT_APPLICABLE_REASON = [
    ("fixed_task_pricing", "fixed_task_pricing"),
    ("tenant_not_billing", "tenant_not_billing"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("usage", "0037_a_cost_settles_once_and_the_table_holds_it"),
    ]

    operations = [
        # 1. NULL becomes sayable. No row moves.
        migrations.AlterField(
            model_name="posting",
            name="billed_cost_micros",
            field=models.BigIntegerField(blank=True, default=0, null=True),
        ),
        # 2. The status, carrying `known` onto every row that already exists.
        migrations.AddField(
            model_name="posting",
            name="pricing_status",
            field=models.CharField(choices=PRICING_STATUS, default="known",
                                   max_length=32),
        ),
        # 3. The reason, which only a `not_applicable` row may carry.
        migrations.AddField(
            model_name="posting",
            name="not_applicable_reason",
            field=models.CharField(blank=True, choices=NOT_APPLICABLE_REASON,
                                   max_length=32, null=True),
        ),
        # 4-5. The two closed sets, at the database.
        migrations.AddConstraint(
            model_name="posting",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("pricing_status__in",
                     ["known", "not_applicable", "unknown", "waived"])),
                name="ck_posting_pricing_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="posting",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("not_applicable_reason__isnull", True),
                    ("not_applicable_reason__in",
                     ["fixed_task_pricing", "tenant_not_billing"]),
                    _connector="OR",
                ),
                name="ck_posting_not_applicable_reason",
            ),
        ),
        # 6. The four legal combinations, and there are only four.
        migrations.AddConstraint(
            model_name="posting",
            constraint=models.CheckConstraint(
                # ⚠ The three terms of each branch are in the order Django's
                # own `Q(**kwargs)` puts them — sorted by lookup — because a
                # migration states the condition as POSITIONAL args, which are
                # not sorted, and the autodetector compares the two
                # deconstructions element by element. Written in the reading
                # order of the table above, this file would be a permanent
                # `makemigrations --check` failure that no schema change fixes.
                condition=models.Q(
                    models.Q(("billed_cost_micros__isnull", False),
                             ("not_applicable_reason__isnull", True),
                             ("pricing_status", "known")),
                    models.Q(("billed_cost_micros__isnull", True),
                             ("not_applicable_reason__isnull", True),
                             ("pricing_status", "waived")),
                    models.Q(("billed_cost_micros__isnull", True),
                             ("not_applicable_reason__isnull", True),
                             ("pricing_status", "unknown")),
                    models.Q(("billed_cost_micros__isnull", True),
                             ("not_applicable_reason__isnull", False),
                             ("pricing_status", "not_applicable")),
                    _connector="OR",
                ),
                name="ck_posting_pricing_status_agrees_with_the_price",
            ),
        ),
    ]
