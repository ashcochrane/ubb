# The clean cut (issue #37): the billed-denominated per-run default limit
# retires unreplaced (task limits are COGS-denominated and default from
# RiskConfig.default_task_provider_cost_limit_micros); the floor-snapshot
# default sheds the retired "hard stop" vocabulary.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_billing", "0007_populate_billing_tenant_config"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="billingtenantconfig", name="run_cost_limit_micros"),
        migrations.RenameField(
            model_name="billingtenantconfig",
            old_name="hard_stop_balance_micros",
            new_name="default_task_floor_snapshot_micros",
        ),
    ]
