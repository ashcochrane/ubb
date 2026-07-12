import uuid

import django.db.models.deletion
from django.db import migrations, models

import apps.billing.gating.models


class Migration(migrations.Migration):
    dependencies = [
        ("gating", "0001_initial"),
        ("customers", "0009_rename_arrears_to_min_balance"),
        ("tenants", "0009_tenant_default_currency"),
    ]
    operations = [
        migrations.AddField(model_name="riskconfig", name="gate_fail_closed",
                            field=models.BooleanField(default=False)),
        migrations.CreateModel(
            name="BudgetConfig",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("cap_micros", models.BigIntegerField(default=0)),
                ("period", models.CharField(default="month", max_length=10)),
                ("enforce_mode", models.CharField(
                    choices=[("advisory", "Advisory"), ("enforcing", "Enforcing")],
                    default="advisory", max_length=10)),
                ("hard_stop_pct", models.IntegerField(default=100)),
                ("alert_levels", models.JSONField(default=apps.billing.gating.models.default_alert_levels)),
                ("fail_closed", models.BooleanField(default=False)),
                ("customer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name="budget_configs", to="customers.customer")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="budget_configs", to="tenants.tenant")),
            ],
            options={"db_table": "ubb_budget_config"},
        ),
        migrations.AddConstraint(model_name="budgetconfig",
            constraint=models.UniqueConstraint(fields=("tenant",), condition=models.Q(customer__isnull=True),
                name="uq_budget_config_tenant_default")),
        migrations.AddConstraint(model_name="budgetconfig",
            constraint=models.UniqueConstraint(fields=("tenant", "customer"), condition=models.Q(customer__isnull=False),
                name="uq_budget_config_tenant_customer")),
    ]
