import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("subscriptions", "0002_create_cost_accumulator_and_economics"),
        ("customers", "0009_rename_arrears_to_min_balance"),
    ]
    operations = [
        migrations.RemoveField(model_name="customercostaccumulator", name="total_cost_micros"),
        migrations.AddField(model_name="customercostaccumulator", name="total_provider_cost_micros",
                            field=models.BigIntegerField(default=0)),
        migrations.AddField(model_name="customercostaccumulator", name="total_billed_cost_micros",
                            field=models.BigIntegerField(default=0)),
        migrations.RemoveField(model_name="customereconomics", name="usage_cost_micros"),
        migrations.AddField(model_name="customereconomics", name="usage_billed_micros",
                            field=models.BigIntegerField(default=0)),
        migrations.AddField(model_name="customereconomics", name="provider_cost_micros",
                            field=models.BigIntegerField(default=0)),
        migrations.AddField(model_name="customereconomics", name="is_unprofitable",
                            field=models.BooleanField(default=False)),
        migrations.AddField(model_name="stripesubscription", name="quantity",
                            field=models.IntegerField(default=1)),
        migrations.CreateModel(
            name="CustomerRevenueProfile",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("recurring_amount_micros", models.BigIntegerField(default=0)),
                ("interval", models.CharField(default="month", max_length=10)),
                ("currency", models.CharField(default="usd", max_length=3)),
                ("effective_from", models.DateField()),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="revenue_profiles", to="customers.customer")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="revenue_profiles", to="tenants.tenant")),
            ],
            options={"db_table": "ubb_customer_revenue_profile"},
        ),
        migrations.AddConstraint(model_name="customerrevenueprofile",
            constraint=models.UniqueConstraint(fields=("tenant", "customer"),
                name="uq_revenue_profile_tenant_customer")),
        migrations.CreateModel(
            name="MarginThresholdConfig",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("min_margin_pct", models.DecimalField(decimal_places=2, default=0, max_digits=6)),
                ("consecutive_periods", models.IntegerField(default=1)),
                ("provider_cost_spike_pct", models.DecimalField(decimal_places=2, default=25, max_digits=6)),
                ("customer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name="margin_thresholds", to="customers.customer")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="margin_thresholds", to="tenants.tenant")),
            ],
            options={"db_table": "ubb_margin_threshold_config"},
        ),
        migrations.AddConstraint(model_name="marginthresholdconfig",
            constraint=models.UniqueConstraint(fields=("tenant",), condition=models.Q(customer__isnull=True),
                name="uq_margin_threshold_tenant_default")),
        migrations.AddConstraint(model_name="marginthresholdconfig",
            constraint=models.UniqueConstraint(fields=("tenant", "customer"), condition=models.Q(customer__isnull=False),
                name="uq_margin_threshold_tenant_customer")),
    ]
