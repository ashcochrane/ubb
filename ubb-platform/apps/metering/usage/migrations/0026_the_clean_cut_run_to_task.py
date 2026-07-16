# The clean cut (issue #37): UsageEvent names the exact unit of work via a
# single task FK; RawIngestEvent rides along.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("usage", "0025_widen_rawingestevent_idempotency_key"),
        ("tasks", "0004_the_clean_cut_run_to_task"),
    ]

    operations = [
        migrations.RenameField(
            model_name="usageevent",
            old_name="run",
            new_name="task",
        ),
        migrations.RenameField(
            model_name="rawingestevent",
            old_name="run_id",
            new_name="task_id",
        ),
    ]
