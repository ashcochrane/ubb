from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gating", "0006_stop_signal_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="stopsignalstate",
            name="announce_outbox_id",
            field=models.UUIDField(blank=True, null=True),
        ),
    ]
