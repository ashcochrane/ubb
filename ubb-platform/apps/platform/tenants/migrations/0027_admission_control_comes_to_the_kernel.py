"""Admission control's one setting arrives on the tenant row (#462, slice 6
§1, §6; #154 §3.4; #141 §4.5).

The per-minute bound on new top-level starts lived on billing's risk row as
`max_requests_per_minute`, which put a control billing does not own on a row
a tenant without billing never has — and the composition layer reached that
row only inside the money-shaped verdict, so a tenant that does not bill
through UBB had no bound at all. A bound on how fast work enters is a
property of the work's admission, a kernel concept, so it joins the tenant's
other kernel rungs here under the name #154 §3.4 coined and is read by
`work/admission.py` for every start.

**PURE ADDITION HERE; THE DATA ARRIVES IN THE NEXT STEP.** The column takes
NULL — the honest record of a tenant that declares no bound, which is what
the risk row's absence used to mean — and `apps.billing.gating`'s `0015`
then carries every value the risk row held onto this column before dropping
its own. Splitting the move across two apps is what a cross-app column move
looks like under ADR-0007 §1 (the shape `0026` and `gating/0011` set for the
two ceiling rungs in #453): the column has to exist in the
kernel's migration graph before the product's migration can write to it and
remove its own.

**THE REVERSE IS EXACT**: drop the column. Run `gating/0015`'s reverse first
and the values are back on the risk row.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0026_the_default_ceilings_for_undeclared_work_come_to_the_kernel"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="max_task_starts_per_minute",
            field=models.PositiveIntegerField(blank=True, default=None, null=True),
        ),
    ]
