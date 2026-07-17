import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gating", "0005_subtask_containment"),
        ("customers", "0014_customer_suspension_reason"),
        ("tenants", "0018_the_clean_cut_run_to_task"),
    ]
    operations = [
        migrations.CreateModel(
            name="StopSignalState",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("family", models.CharField(
                    choices=[("floor_stop", "Floor stop"), ("soft_floor", "Soft floor")], max_length=20)),
                ("state", models.CharField(
                    choices=[("stopped", "Stopped"), ("cleared", "Cleared")], max_length=10)),
                ("episode_seq", models.BigIntegerField(default=0)),
                ("reason", models.CharField(blank=True, default="", max_length=64)),
                ("transitioned_at", models.DateTimeField()),
                ("owner", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="stop_signal_states", to="customers.customer")),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="stop_signal_states", to="tenants.tenant")),
            ],
            options={"db_table": "ubb_stop_signal_state"},
        ),
        migrations.AddConstraint(
            model_name="stopsignalstate",
            constraint=models.UniqueConstraint(
                fields=("owner", "family"), name="uq_stop_signal_owner_family"),
        ),
    ]
