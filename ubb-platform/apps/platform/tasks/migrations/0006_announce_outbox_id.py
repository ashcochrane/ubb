from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0005_subtask_containment"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="announce_outbox_id",
            field=models.UUIDField(blank=True, null=True),
        ),
    ]
