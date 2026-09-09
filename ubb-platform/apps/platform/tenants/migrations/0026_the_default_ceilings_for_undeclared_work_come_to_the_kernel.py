"""The tenant's two default COGS ceilings — one per altitude, for work with no
declared kind — arrive on the tenant row (#453, slice 6 §2, #141 §6.2, §7).

They lived on billing's risk row, which put a control billing does not own on
a row a tenant without billing never has (#141 §4.4: *"not one step is
billing"*). They join the tenant's two deadline rungs here because that is the
precedent #141 §6.2 named: a bound on a unit of work is a kernel setting the
platform sweepers and the start's ceiling ladder read without importing a
product.

**PURE ADDITION HERE; THE DATA ARRIVES IN THE NEXT STEP.** Both columns take
NULL — the honest record of a tenant that has declared no default — and
`apps.billing.gating`'s `0011` then carries every value the risk row held onto
these columns before dropping its own. Splitting the move across two apps is
what a cross-app column move looks like under ADR-0007 §1: the column has to
exist in the kernel's migration graph before the product's migration can write
to it and remove its own.

**WHY `default_`, WHEN THE TWO RUNGS ABOVE CARRY NO PREFIX.** The silence
window and the absolute deadline are middle rungs UNDER a declaration — a kind
of work that says nothing about its window inherits the tenant's. These two
are not: a declared kind of work must state its own ceiling or declare itself
uncapped, so they are consulted for work with NO declared kind only, and the
prefix says what that difference is. `default_task_cogs_ceiling_micros` is also
the name #154 §3.4 coined, landing where a default actually lives; the
declaration's own column dropped the prefix in `work/0024` because a declared
value is the ceiling, not a default for one.

**THE REVERSE IS EXACT**: drop both columns. Run `gating/0011`'s reverse first
and the values are back on the risk row.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0025_the_two_expiry_windows_get_a_tenant_rung"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="default_task_cogs_ceiling_micros",
            field=models.BigIntegerField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name="tenant",
            name="default_subtask_cogs_ceiling_micros",
            field=models.BigIntegerField(blank=True, default=None, null=True),
        ),
    ]
