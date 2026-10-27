"""A tenant's currency is US dollars (#555).

UBB v1 is US dollars only (ADR-0023, #555). The doors refuse another currency
through `core.currency_policy.admit_currency`; this is the database's half, so
a write that goes round them — the admin form, `QuerySet.update()`, `psql` —
meets the same rule.

`ubb_tenant.default_currency` is the column the ruling named: the admin form
edits every column of a tenant, and with this constraint the currency lock
has nothing left to guard — a tenant cannot leave USD by any path, so it
retires (#555's ruling; the owner's ruling 4 of 2026-10-26).

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
        ("tenants", "0027_admission_control_comes_to_the_kernel"),
    ]

    operations = [
        migrations.RunPython(
            refuse_rows_outside_the_policy("ubb_tenant", "default_currency"),
            migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="tenant",
            constraint=models.CheckConstraint(
                condition=models.Q(default_currency="usd"),
                name="ck_tenant_default_currency_usd")),
    ]
