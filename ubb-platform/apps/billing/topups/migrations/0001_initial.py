from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("customers", "0007_remove_wallet_to_billing"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="AutoTopUpConfig",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("deleted_at", models.DateTimeField(blank=True, db_index=True, default=None, null=True)),
                        ("customer", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="auto_top_up_config", to="customers.customer")),
                        ("is_enabled", models.BooleanField(default=False)),
                        ("trigger_threshold_micros", models.BigIntegerField(default=10000000)),
                        ("top_up_amount_micros", models.BigIntegerField(default=20000000)),
                    ],
                    options={
                        "db_table": "ubb_auto_top_up_config",
                    },
                ),
                migrations.CreateModel(
                    name="TopUpAttempt",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="top_up_attempts", to="customers.customer")),
                        ("amount_micros", models.PositiveBigIntegerField()),
                        ("trigger", models.CharField(choices=[("manual", "Manual"), ("auto_topup", "Auto Top-Up"), ("widget", "Widget")], max_length=20)),
                        ("status", models.CharField(choices=[("pending", "Pending"), ("succeeded", "Succeeded"), ("failed", "Failed"), ("expired", "Expired")], db_index=True, default="pending", max_length=20)),
                        ("stripe_payment_intent_id", models.CharField(blank=True, max_length=255, null=True)),
                        ("stripe_checkout_session_id", models.CharField(blank=True, max_length=255, null=True)),
                        ("failure_reason", models.JSONField(blank=True, null=True)),
                    ],
                    options={
                        "db_table": "ubb_top_up_attempt",
                    },
                ),
                migrations.AddConstraint(
                    model_name="topupattempt",
                    constraint=models.UniqueConstraint(
                        condition=models.Q(("status", "pending"), ("trigger", "auto_topup")),
                        fields=("customer",),
                        name="uq_one_pending_auto_topup_per_customer",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
