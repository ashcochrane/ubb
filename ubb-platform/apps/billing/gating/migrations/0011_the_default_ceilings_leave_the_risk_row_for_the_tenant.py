"""The two tenant-default COGS ceilings leave billing's risk row, carrying
their values onto the tenant row first (#453, slice 6 §1/§2, #141 §7).

**THE VALUES ARE CARRIED, THEN THE COLUMNS GO (ADR-0007 §1).** For every risk
row holding a default at either altitude, the same figure is written onto its
tenant's `default_task_cogs_ceiling_micros` / `default_subtask_cogs_ceiling_micros`
(added by `tenants/0026`) before the risk row's columns are removed. A risk
row holding NULL at an altitude writes nothing: the tenant column already
holds NULL, which means the same thing on both rows — no default declared.
Only rows that carry a value are touched, so the forward pass is proportional
to tenants that ever configured one.

**WHAT THE MOVE CHANGES IN MEANING, STATED.** On the risk row these were the
third rung of every ladder: a declared kind of work with no ceiling fell
through to them. On the tenant row they apply to work with NO declared kind
only (`work/0024` makes a declaration answer for itself). No value is
reinterpreted here — a tenant that had a default keeps it, at the same figure
— but what it is consulted FOR narrows, and `work/0024`'s backfill is what
keeps the declared kinds honest through that narrowing.

**THE REVERSE CARRIES THEM BACK.** The columns are re-added to the risk row and
every tenant holding a default at either altitude has it written back —
creating the risk row where the tenant has none, because on the old model the
default could only ever be recorded there. Then `tenants/0026`'s reverse may
drop the tenant columns. Exact in both directions for every row that carried a
value.
"""

from django.db import migrations

#: (the risk row's column, under the retired spelling this app's history
#: still holds it by) -> (the tenant row's column, under the canonical name).
RUNGS = (
    ("default_task_provider_cost_limit_micros", "default_task_cogs_ceiling_micros"),
    ("default_subtask_provider_cost_limit_micros", "default_subtask_cogs_ceiling_micros"),
)


def carry_the_defaults_onto_the_tenant(apps, schema_editor):
    RiskConfig = apps.get_model("gating", "RiskConfig")
    Tenant = apps.get_model("tenants", "Tenant")
    columns = [risk_column for risk_column, _ in RUNGS]
    for row in RiskConfig.objects.only("tenant_id", *columns).iterator():
        carried = {tenant_column: getattr(row, risk_column)
                   for risk_column, tenant_column in RUNGS
                   if getattr(row, risk_column) is not None}
        if carried:
            Tenant.objects.filter(pk=row.tenant_id).update(**carried)


def carry_the_defaults_back_onto_the_risk_row(apps, schema_editor):
    RiskConfig = apps.get_model("gating", "RiskConfig")
    Tenant = apps.get_model("tenants", "Tenant")
    columns = [tenant_column for _, tenant_column in RUNGS]
    holding = Tenant.objects.only("id", *columns).exclude(
        **{f"{column}__isnull": True for column in columns})
    for tenant in holding.iterator():
        carried = {risk_column: getattr(tenant, tenant_column)
                   for risk_column, tenant_column in RUNGS
                   if getattr(tenant, tenant_column) is not None}
        RiskConfig.objects.update_or_create(tenant_id=tenant.pk, defaults=carried)


class Migration(migrations.Migration):

    dependencies = [
        ("gating", "0010_budget_enforce_mode_rename"),
        ("tenants", "0026_the_default_ceilings_for_undeclared_work_come_to_the_kernel"),
    ]

    operations = [
        migrations.RunPython(carry_the_defaults_onto_the_tenant,
                             carry_the_defaults_back_onto_the_risk_row),
        migrations.RemoveField(
            model_name="riskconfig",
            name="default_task_provider_cost_limit_micros",
        ),
        migrations.RemoveField(
            model_name="riskconfig",
            name="default_subtask_provider_cost_limit_micros",
        ),
    ]
