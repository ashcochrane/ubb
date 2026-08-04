from django.db import migrations, models


class Migration(migrations.Migration):

    # App label moved 'tasks' -> 'work' (#196); see 0001_initial for why
    # this replaces its predecessor rather than re-running it.
    replaces = [("tasks", "0006_announce_outbox_id")]

    dependencies = [
        ("work", "0005_subtask_containment"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="announce_outbox_id",
            field=models.UUIDField(blank=True, null=True),
        ),
    ]
