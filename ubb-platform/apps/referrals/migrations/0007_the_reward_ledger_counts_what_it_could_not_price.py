"""The reward ledger counts what it could not PRICE (#351).

The mirror of `0006_the_reward_ledger_counts_what_it_could_not_read`, for the
other amount the reconciler reads. `Posting.billed_cost_micros` becomes nullable
in #351, and the reconciler's `or 0` over it was a guard against nothing while
the column could not be null — the day it could, a referred customer's spend
would have read complete with a charge missing from it, and the referrer's
reward computed against the smaller number.

The skip stays: there is no amount to add, and inventing one would pay a reward
on a charge nobody has resolved. This column is the record that it happened.

A SECOND COLUMN, because the two counts point in opposite directions. An
unresolved supplier cost makes `reward_micros` a figure that could move either
way when the cost arrives; an unresolved customer price makes it a FLOOR — the
referrer is owed at least that much. One number could not say which.

Every existing row gets zero, and zero is truthful: nothing could write an
unresolved price before this slice.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("referrals", "0006_the_reward_ledger_counts_what_it_could_not_read"),
    ]

    operations = [
        migrations.AddField(
            model_name="referralrewardledger",
            name="unpriced_event_count",
            field=models.IntegerField(default=0),
        ),
    ]
