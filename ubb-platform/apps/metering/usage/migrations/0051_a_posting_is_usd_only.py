"""A posting is denominated in US dollars (#555).

UBB v1 is US dollars only (ADR-0023, #555). The doors refuse another currency
through `core.currency_policy.admit_currency`; this is the database's half, so
a write that goes round them — the admin form, `QuerySet.update()`, `psql` —
meets the same rule.

`ubb_posting.currency` carries no transition rule, so no trigger on this table
names it and this `CHECK` is the whole of what holds it. None of the table's
triggers is touched.

**Pre-cutover data is reconciled by refusing, never by rewriting.** Before a
`CHECK` is installed, `refuse_rows_outside_the_policy` stops the migration if
any row holds another value, and names them. There is no FX to convert with
and a relabel would lie, so the honest reconciliation is a person deciding
about each row. Nothing is deployed, so on every real database the step finds
nothing.

**The reverse is exact**: drop what was added. No row is
rewritten either way.
"""

from django.db import migrations, models

from core.currency_policy import refuse_rows_outside_the_policy


class Migration(migrations.Migration):

    dependencies = [
        ("usage", "0050_a_held_price_states_its_reason"),
    ]

    operations = [
        migrations.RunPython(
            refuse_rows_outside_the_policy("ubb_posting", "currency"),
            migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="posting",
            constraint=models.CheckConstraint(
                condition=models.Q(currency="usd"),
                name="ck_posting_currency_usd")),
    ]
