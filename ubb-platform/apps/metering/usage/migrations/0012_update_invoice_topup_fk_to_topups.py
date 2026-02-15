from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("topups", "0001_initial"),
        ("usage", "0011_usage_event_group_keys_gin_index"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="invoice",
                    name="top_up_attempt",
                    field=models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invoice",
                        to="topups.topupattempt",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
