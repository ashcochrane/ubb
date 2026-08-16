"""The monthly cost total and its snapshot record what they excluded (#328).

Both columns are the same fact one step apart: the accumulator counts the
postings whose supplier cost UBB had not resolved when the event arrived, and
the snapshot copies that count beside the total it froze. Without the pair, a
margin over a partial cost reads as a margin rather than as the ceiling it is,
and the cost-spike comparison divides by a denominator that is too small.

Every existing row gets zero. That is the truthful answer rather than a
convenient one: nothing wrote an unresolved cost before #320, and for the rows
recorded since, what the running total left out was never recorded anywhere —
it was added to event by event, so there is nothing to backfill FROM. The hourly
accumulator reconcile rebuilds any open period from the postings themselves.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0011_plan_to_kernel"),
    ]

    operations = [
        migrations.AddField(
            model_name="customercostaccumulator",
            name="unresolved_event_count",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="customereconomics",
            name="unresolved_event_count",
            field=models.IntegerField(default=0),
        ),
    ]
