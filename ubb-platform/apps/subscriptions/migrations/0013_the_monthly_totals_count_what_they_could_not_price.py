"""The monthly totals count what they could not PRICE (#351).

The mirror of `0012_the_monthly_totals_count_what_they_left_out` for the other
side of the margin. `Posting.billed_cost_micros` becomes nullable in #351, so
the accumulator stops folding an absent price into its running billed total —
which without a column here would leave that total a FLOOR reading like a
figure, and the snapshot taken from it a floor too.

TWO COLUMNS RATHER THAN ONE COUNT SERVING BOTH, because the two are about
different events: a posting can carry a settled supplier cost and a customer
price UBB could not resolve. They also bound the derived figures in OPPOSITE
directions — an excluded cost makes `gross_margin_micros` a ceiling, an excluded
price makes it a floor — so a single number could not even say which way the
margin is wrong.

Every existing row gets zero, and zero is truthful for all of them: nothing
could write an unresolved price before this slice.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0012_the_monthly_totals_count_what_they_left_out"),
    ]

    operations = [
        migrations.AddField(
            model_name="customercostaccumulator",
            name="unpriced_event_count",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="customereconomics",
            name="unpriced_event_count",
            field=models.IntegerField(default=0),
        ),
    ]
