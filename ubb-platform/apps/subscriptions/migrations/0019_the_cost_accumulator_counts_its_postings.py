"""The monthly cost accumulator's count is named for what it counts (R10-W4).

`CustomerCostAccumulator` adds one for every `usage.recorded` event whatever
its kind — a Task Charge's projection writes that event too — and the hourly
repair takes the figure from a count over every posting. It is a count of the
postings its totals add up, not the `recorded_events` measure, so ruling 1 of
R10-W4 names it `posting_count`, as it names the posting-count reads.

One operation, `RenameField` (ADR-0007 §1): the column moves with every stored
value intact, and the reverse is exact.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0018_a_foreign_currency_subscription_is_kept_and_quarantined"),
    ]

    operations = [
        migrations.RenameField(
            model_name="customercostaccumulator",
            old_name="event_count",
            new_name="posting_count",
        ),
    ]
