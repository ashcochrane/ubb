"""A Plan cannot exist without naming the Pricing Book it prices from (#362, #151 §7.2).

**The column.** A Plan names the Pricing Book its customers are priced from,
and it is `NOT NULL`. Assigning a plan becomes all it takes to price a
customer: resolution reads that book at the ladder's selected-book source, and
the record that assigns a book to a customer outright can therefore be deleted
by ticket 21.

**NOT NULLABLE, AND THE ARGUMENT IS THE WHOLE POINT.** A nullable reference
produces an alert nobody can act on, because *"this plan has no book"* is
indistinguishable from *"this plan does not price usage"*. Required makes the
second case expressible honestly — a book holding no rules — instead of leaving
one null standing for two different facts. What such a plan's customers are
then charged is the markup rung's answer rather than this column's; the model's
own comment says which rung that is today and which ticket moves it.

⚠ **NO DATA MIGRATION, NO BACKFILL AND NO HEURISTIC, DELIBERATELY.** Two
documents flagged that a migration cannot distinguish a plan's *absent* markup
from a *deliberate* zero, because both are `0` in the column, and inferring a
book from that would be guessing. **That question is moot here:** UBB is
deployed nowhere, holds no tenant data, and the migrations squash at cutover
(#155 §11). So this adds the column `NOT NULL` with no default and no
`RunPython` — the honest operation against an empty table — rather than
shipping a nullable column plus a backfill that could only ever guess.

⚠ **HAND-WRITTEN.** `makemigrations` only asks about a new non-null column on a
TTY; run non-interactively it writes a one-off default into the schema, and
there is no default to offer here — a plan's book is a thing a tenant's
catalogue supplies, not a value a migration can invent. ADR-0007 §1 is NOT the
authority for that: it governs migrations that rename or MOVE a column, and
this one adds a column and moves nothing. What §1 does settle is the shape this
is not — no `AddField` + `RemoveField` pair, because nothing is being renamed.

**`PROTECT`, the way a pricing rule already holds the book it lives in.** A
book a plan prices from may not be
deleted out from under it: the plan would then be a plan with no pricing, which
is exactly the state the `NOT NULL` exists to make unreachable.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("plans", "0001_initial"),
        # The book this points at. Its latest migration rather than its initial
        # one, so the reference is against the container as this slice has
        # already reshaped it.
        ("pricing", "0024_a_customer_override_replaces_a_whole_rule"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="pricing_book",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="plans",
                to="pricing.ratecard",
            ),
        ),
    ]
