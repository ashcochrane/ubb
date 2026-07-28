# Task 2 (billing-surface-correctness): BudgetConfig.enforce_mode values stop
# colliding with the retired Tenant.enforcement_mode vocabulary (`advisory` was
# mapped to `off` there by tenants migration 0019) and say what they actually
# do: `advisory` -> `alert_only` (emits threshold alerts, never refuses
# anything), `enforcing` -> `blocking` (refuses new task starts; on postpaid
# additionally stops running work). Clean cut, pre-live: no aliases, no
# dual-read. The data map runs before the choices narrow so no row is ever
# stranded on a retired value.
from django.db import migrations, models


def rename_forward(apps, schema_editor):
    BudgetConfig = apps.get_model("gating", "BudgetConfig")
    BudgetConfig.objects.filter(enforce_mode="advisory").update(enforce_mode="alert_only")
    BudgetConfig.objects.filter(enforce_mode="enforcing").update(enforce_mode="blocking")


def rename_reverse(apps, schema_editor):
    BudgetConfig = apps.get_model("gating", "BudgetConfig")
    BudgetConfig.objects.filter(enforce_mode="alert_only").update(enforce_mode="advisory")
    BudgetConfig.objects.filter(enforce_mode="blocking").update(enforce_mode="enforcing")


class Migration(migrations.Migration):

    dependencies = [
        ("gating", "0009_livebalancerepair"),
    ]

    operations = [
        migrations.RunPython(rename_forward, rename_reverse),
        migrations.AlterField(
            model_name="budgetconfig",
            name="enforce_mode",
            field=models.CharField(
                choices=[("alert_only", "Alert only"), ("blocking", "Blocking")],
                default="alert_only",
                max_length=10,
            ),
        ),
    ]
