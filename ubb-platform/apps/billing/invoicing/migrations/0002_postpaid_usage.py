import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("invoicing", "0001_initial"),
        ("customers", "0009_rename_arrears_to_min_balance"),
        ("tenants", "0009_tenant_default_currency"),
    ]
    operations = [
        migrations.CreateModel(
            name="CustomerUsageInvoice",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("period_start", models.DateField()),
                ("period_end", models.DateField()),
                ("total_billed_micros", models.BigIntegerField(default=0)),
                ("currency", models.CharField(default="usd", max_length=3)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("pushing", "Pushing"),
                    ("pushed", "Pushed"), ("skipped", "Skipped"), ("failed", "Failed")],
                    db_index=True, default="pending", max_length=10)),
                ("stripe_invoice_id", models.CharField(blank=True, default="", max_length=255)),
                ("skip_reason", models.CharField(blank=True, default="", max_length=50)),
                ("pushed_at", models.DateTimeField(blank=True, null=True)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="usage_invoices", to="customers.customer")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="usage_invoices", to="tenants.tenant")),
            ],
            options={"db_table": "ubb_customer_usage_invoice"},
        ),
        migrations.AddConstraint(model_name="customerusageinvoice",
            constraint=models.UniqueConstraint(fields=("customer", "period_start"),
                name="uq_usage_invoice_customer_period")),
        migrations.CreateModel(
            name="UsageInvoiceLineItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("dimension", models.CharField(blank=True, default="", max_length=255)),
                ("amount_micros", models.BigIntegerField(default=0)),
                ("stripe_invoice_item_id", models.CharField(blank=True, default="", max_length=255)),
                ("usage_invoice", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="line_items", to="invoicing.customerusageinvoice")),
            ],
            options={"db_table": "ubb_usage_invoice_line_item"},
        ),
        migrations.CreateModel(
            name="PostpaidUsageConfig",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("usage_line_item_group_by", models.CharField(blank=True, default="", max_length=64)),
                ("tenant", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                    related_name="postpaid_config", to="tenants.tenant")),
            ],
            options={"db_table": "ubb_postpaid_usage_config"},
        ),
    ]
