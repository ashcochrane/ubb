"""A reported cost pins US dollars, or names no code (#555).

UBB v1 is US dollars only (ADR-0023, #555). The doors refuse another currency
through `core.currency_policy.admit_currency`; this is the database's half, so
a write that goes round them — the admin form, `QuerySet.update()`, `psql` —
meets the same rule.

The empty string stays legal: it is the column saying a path into the
supplier's response names the currency instead, which
`ck_reported_cost_currency_pinned_once` already holds exclusive with a pinned
code. What a supplier returns there is held where it lands — the recording
routes refuse any currency but US dollars.

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
        ("event_types", "0012_a_publication_keeps_its_supplier"),
    ]

    operations = [
        migrations.RunPython(
            refuse_rows_outside_the_policy("ubb_reported_cost_mapping", "currency", or_blank=True),
            migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="reportedcostmapping",
            constraint=models.CheckConstraint(
                condition=models.Q(currency="usd") | models.Q(currency=""),
                name="ck_reported_cost_currency_usd")),
    ]
