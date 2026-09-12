"""The per-minute bound on new work leaves billing's risk row, carrying each
tenant's value onto the tenant row first (#462, slice 6 §1, §6; #154 §3.4).

**THE VALUES ARE CARRIED, THEN THE COLUMN GOES (ADR-0007 §1).** For every
risk row holding a bound above zero, the same figure is written onto its
tenant's `max_task_starts_per_minute` (added by `tenants/0027`) before the
risk row's column is removed. A risk row holding zero writes nothing: on the
old row zero meant the bound was switched off, and on the tenant row that is
NULL — which the tenant column already holds. A tenant with no risk row at
all had no bound either, and keeps none. Only rows that carry a bound are
touched, so the forward pass is proportional to tenants that ever configured
one.

**WHAT THE MOVE CHANGES IN MEANING, STATED.** On the risk row the bound ran
inside billing's money-shaped verdict, which the composition layer asks only
for a tenant with a wallet; on the tenant row it is read by the kernel's
admission check for EVERY start. No value is reinterpreted — a tenant that
had a bound keeps it, at the same figure, in the same window, keyed per seat
as before — but who is subject to it widens to every tenant, which is the
point of the move. The old row's zero-means-off convention does not travel:
the tenant configuration route refuses zero, and NULL is the one spelling of
"no bound".

**THE REVERSE CARRIES THEM BACK.** The column is re-added to the risk row at
its old default and every tenant holding a bound has it written back —
creating the risk row where the tenant has none, because on the old model a
bound could only ever be recorded there. A tenant holding NULL whose risk row
exists gets zero, the old spelling of "no bound", rather than the column's
default of sixty: the default was the row's opinion for a tenant that had
never said, and NULL is a tenant that has. Exact in both directions for every
row that carried a value.

**WHAT THE RISK ROW IS NOW.** One column, `gate_fail_closed` — the posture
the pool read takes when its store is away (#150 §15) — and the model's
docstring says so.
"""

from django.db import migrations, models

#: The risk row's column, under the spelling this app's history holds it by,
#: and the tenant row's column under the canonical name.
RISK_COLUMN = "max_requests_per_minute"
TENANT_COLUMN = "max_task_starts_per_minute"

#: The risk row's spelling of "no bound", which the tenant row spells NULL.
SWITCHED_OFF = 0


def carry_the_bound_onto_the_tenant(apps, schema_editor):
    RiskConfig = apps.get_model("gating", "RiskConfig")
    Tenant = apps.get_model("tenants", "Tenant")
    holding = (RiskConfig.objects.only("tenant_id", RISK_COLUMN)
               .filter(**{f"{RISK_COLUMN}__gt": SWITCHED_OFF}))
    for row in holding.iterator():
        Tenant.objects.filter(pk=row.tenant_id).update(
            **{TENANT_COLUMN: getattr(row, RISK_COLUMN)})


def carry_the_bound_back_onto_the_risk_row(apps, schema_editor):
    RiskConfig = apps.get_model("gating", "RiskConfig")
    Tenant = apps.get_model("tenants", "Tenant")
    for tenant in Tenant.objects.only("id", TENANT_COLUMN).iterator():
        bound = getattr(tenant, TENANT_COLUMN)
        if bound is not None:
            RiskConfig.objects.update_or_create(
                tenant_id=tenant.pk, defaults={RISK_COLUMN: bound})
        else:
            RiskConfig.objects.filter(tenant_id=tenant.pk).update(
                **{RISK_COLUMN: SWITCHED_OFF})


class Migration(migrations.Migration):

    dependencies = [
        ("gating", "0014_the_signal_ledger_keys_by_family_and_line"),
        ("tenants", "0027_admission_control_comes_to_the_kernel"),
    ]

    operations = [
        migrations.RunPython(carry_the_bound_onto_the_tenant,
                             carry_the_bound_back_onto_the_risk_row),
        migrations.RemoveField(
            model_name="riskconfig",
            name=RISK_COLUMN,
        ),
    ]
