"""A wallet and a credit grant hold US dollars (#555).

UBB v1 is US dollars only (ADR-0023, #555). The doors refuse another currency
through `core.currency_policy.admit_currency`; this is the database's half, so
a write that goes round them — the admin form, `QuerySet.update()`, `psql` —
meets the same rule.

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
        ("wallets", "0011_a_prepaid_start_reserves_the_agreed_price"),
    ]

    operations = [
        migrations.RunPython(
            refuse_rows_outside_the_policy("ubb_wallet", "currency"),
            migrations.RunPython.noop),
        migrations.RunPython(
            refuse_rows_outside_the_policy("ubb_credit_grant", "currency"),
            migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="wallet",
            constraint=models.CheckConstraint(
                condition=models.Q(currency="usd"),
                name="ck_wallet_currency_usd")),
        migrations.AddConstraint(
            model_name="creditgrant",
            constraint=models.CheckConstraint(
                condition=models.Q(currency="usd"),
                name="ck_credit_grant_currency_usd")),
    ]
