# The clean cut (issue #37): the billed-denominated tenant-wide per-label-task
# cap (max_cost_per_task_micros) is dropped; its replacement is the
# COGS-denominated per-registered-task default limit, applied at the
# start-gate when a start call names no explicit limit (null = no default:
# absent both, the unit is uncapped and no signal ever fires).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gating", "0003_riskconfig_max_cost_per_task_micros"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="riskconfig", name="max_cost_per_task_micros"),
        migrations.AddField(
            model_name="riskconfig",
            name="default_task_provider_cost_limit_micros",
            field=models.BigIntegerField(blank=True, null=True),
        ),
    ]
