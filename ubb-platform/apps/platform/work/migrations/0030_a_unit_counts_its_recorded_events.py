"""A unit of work's count is named for what it counts (R10-W4).

`Task`'s count is every metered usage event recorded under the unit, its
contained work's included, and never the Charge's projection (G14 pin 2) —
the registry's `recorded_events` measure at the scope of one unit. Ruling 1 of
R10-W4 renames the published field on the Task reads and the close to that
measure's name, and retires the old one everywhere living, so the column moves
with it.

One operation, `RenameField` (ADR-0007 §1): the column moves with every stored
value intact, and the reverse is exact.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("work", "0029_a_units_stop_and_its_start_are_ubbs_own_record"),
    ]

    operations = [
        migrations.RenameField(
            model_name="task",
            old_name="event_count",
            new_name="recorded_events",
        ),
    ]
