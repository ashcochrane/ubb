"""A rule, a charge and a cost book are denominated in US dollars (#555).

UBB v1 is US dollars only (ADR-0023, #555). The doors refuse another currency
through `core.currency_policy.admit_currency`; this is the database's half, so
a write that goes round them — the admin form, `QuerySet.update()`, `psql` —
meets the same rule.

`uq_cost_book_one_default_per_provider` loses `currency` in the same step, the
drift #555's ruling folded in: a default per supplier PER CURRENCY promised a
capability USD-only refuses. The refusal runs first, so the narrower key is
only ever built over books that could not have collided on currency.

**Pre-cutover data is reconciled by refusing, never by rewriting.** Before a
`CHECK` is installed, `refuse_rows_outside_the_policy` stops the migration if
any row holds another value, and names them. There is no FX to convert with
and a relabel would lie, so the honest reconciliation is a person deciding
about each row. Nothing is deployed, so on every real database the step finds
nothing.

**The reverse is exact**: drop what was added, and put the wider key back. No row is
rewritten either way.
"""

from django.db import migrations, models

from core.currency_policy import refuse_rows_outside_the_policy


class Migration(migrations.Migration):

    dependencies = [
        ("pricing", "0032_an_agreed_price_is_published_with_provenance"),
    ]

    operations = [
        migrations.RunPython(
            refuse_rows_outside_the_policy("ubb_rate", "currency"),
            migrations.RunPython.noop),
        migrations.RunPython(
            refuse_rows_outside_the_policy("ubb_charge", "currency"),
            migrations.RunPython.noop),
        migrations.RunPython(
            refuse_rows_outside_the_policy("ubb_cost_book", "currency"),
            migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="costbook",
            name="uq_cost_book_one_default_per_provider"),
        migrations.AddConstraint(
            model_name="costbook",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_default=True),
                fields=("tenant", "provider_key"),
                name="uq_cost_book_one_default_per_provider")),
        migrations.AddConstraint(
            model_name="rate",
            constraint=models.CheckConstraint(
                condition=models.Q(currency="usd"),
                name="ck_rate_currency_usd")),
        migrations.AddConstraint(
            model_name="charge",
            constraint=models.CheckConstraint(
                condition=models.Q(currency="usd"),
                name="ck_charge_currency_usd")),
        migrations.AddConstraint(
            model_name="costbook",
            constraint=models.CheckConstraint(
                condition=models.Q(currency="usd"),
                name="ck_cost_book_currency_usd")),
    ]
