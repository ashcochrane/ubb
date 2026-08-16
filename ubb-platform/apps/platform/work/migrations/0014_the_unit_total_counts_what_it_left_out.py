"""A work unit records how many of its events it could not cost (#328).

`Posting.provider_cost_micros` became nullable in #317 and the accumulate
primitive stopped adding a zero for the nulls in #320 — which left the unit's
provider total a FLOOR with nothing on the row to say so. This column is that
something.

Every existing row gets zero, and zero is the truthful answer for all of them:
the column that produces an unresolved cost has only existed since #317, and
until #320 nothing wrote one. A backfill would have to invent a number no
posting can supply — the unit total was ADDED to, event by event, so what it
excluded was never recorded anywhere else.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("work", "0013_ten_slots_on_the_task"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="unresolved_event_count",
            field=models.IntegerField(default=0),
        ),
    ]
