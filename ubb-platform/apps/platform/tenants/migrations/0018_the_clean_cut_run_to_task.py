# The clean cut (issue #37): run-era config keys retire. The billed
# per-run default (run_cost_limit_micros) is replaced by the COGS-denominated
# RiskConfig.default_task_provider_cost_limit_micros; the "hard stop"
# floor default moves to BillingTenantConfig.default_task_floor_snapshot_micros
# (these Tenant copies were dead knobs — RiskService reads BillingTenantConfig).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0017_tenant_run_stale_seconds"),
    ]

    operations = [
        migrations.RemoveField(model_name="tenant", name="run_cost_limit_micros"),
        migrations.RemoveField(model_name="tenant", name="hard_stop_balance_micros"),
        migrations.RenameField(
            model_name="tenant",
            old_name="run_stale_seconds",
            new_name="task_stale_seconds",
        ),
    ]
