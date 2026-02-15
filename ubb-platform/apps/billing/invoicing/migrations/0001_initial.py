from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tenants", "0001_initial"),
        ("customers", "0001_initial"),
        ("topups", "0001_initial"),
        ("usage", "0013_remove_invoice_from_state"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Invoice",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("stripe_invoice_id", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                        ("total_amount_micros", models.BigIntegerField(default=0)),
                        ("status", models.CharField(choices=[("draft", "Draft"), ("finalized", "Finalized"), ("paid", "Paid"), ("void", "Void")], db_index=True, default="draft", max_length=20)),
                        ("finalized_at", models.DateTimeField(blank=True, null=True)),
                        ("paid_at", models.DateTimeField(blank=True, null=True)),
                        ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="invoices", to="tenants.tenant")),
                        ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="invoices", to="customers.customer")),
                        ("top_up_attempt", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="invoice", to="topups.topupattempt")),
                    ],
                    options={
                        "db_table": "ubb_invoice",
                    },
                ),
                migrations.AddIndex(
                    model_name="invoice",
                    index=models.Index(fields=["customer", "status"], name="idx_invoice_customer_status"),
                ),
            ],
            database_operations=[],  # Table already exists
        ),
    ]
