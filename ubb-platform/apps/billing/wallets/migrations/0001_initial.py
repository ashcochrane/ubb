from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("customers", "0006_remove_customer_email"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Wallet",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("deleted_at", models.DateTimeField(blank=True, null=True)),
                        ("customer", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="wallet", to="customers.customer")),
                        ("balance_micros", models.BigIntegerField(default=0)),
                        ("currency", models.CharField(default="USD", max_length=3)),
                    ],
                    options={
                        "db_table": "ubb_wallet",
                    },
                ),
                migrations.CreateModel(
                    name="WalletTransaction",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("wallet", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transactions", to="wallets.wallet")),
                        ("transaction_type", models.CharField(choices=[("TOP_UP", "Top Up"), ("USAGE_DEDUCTION", "Usage Deduction"), ("WITHDRAWAL", "Withdrawal"), ("REFUND", "Refund"), ("ADJUSTMENT", "Adjustment")], db_index=True, max_length=20)),
                        ("amount_micros", models.BigIntegerField()),
                        ("balance_after_micros", models.BigIntegerField()),
                        ("description", models.TextField(blank=True, default="")),
                        ("reference_id", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                        ("idempotency_key", models.CharField(blank=True, db_index=True, max_length=500, null=True)),
                    ],
                    options={
                        "db_table": "ubb_wallet_transaction",
                        "ordering": ["-created_at"],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
