"""A work unit records how many of its events it could not price (#351).

The mirror of `0014_the_unit_total_counts_what_it_left_out` for the other side
of the margin. `Posting.billed_cost_micros` becomes nullable in #351, so the
accumulate primitive stops adding a zero for the nulls — which would leave the
unit's billed total a FLOOR with nothing on the row to say so. This column is
that something.

A SECOND COLUMN RATHER THAN ONE COUNT SERVING BOTH, for the reason the two
totals are two columns: they are about different events. A unit can hold a
settled supplier cost and a customer price UBB could not resolve, and one
number answering for both would let either caveat vanish behind the other.

Every existing row gets zero, and zero is the truthful answer for all of them:
nothing could write an unresolved price before this slice, so there is nothing
to backfill. As with 0014, a backfill could not be computed in any case — the
unit total was ADDED to, event by event, so what it excluded was never recorded
anywhere else.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("work", "0014_the_unit_total_counts_what_it_left_out"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="unpriced_event_count",
            field=models.IntegerField(default=0),
        ),
    ]
