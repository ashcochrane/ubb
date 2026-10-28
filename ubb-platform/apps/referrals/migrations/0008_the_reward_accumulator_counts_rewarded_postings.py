"""The reward accumulator's count is named for what it counts (R10-W4).

`ReferralRewardAccumulator` adds one only for a `usage.recorded` posting that
actually earned a reward — never for one that earned nothing, hit the cap or
was skipped (`apps/referrals/handlers.py`). Ruling 1 of R10-W4 retires the
old name everywhere living, and this count is neither the referred customer's
events nor every posting, so it is `rewarded_posting_count`.

One operation, `RenameField` (ADR-0007 §1): the column moves with every stored
value intact, and the reverse is exact.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("referrals", "0007_the_reward_ledger_counts_what_it_could_not_price"),
    ]

    operations = [
        migrations.RenameField(
            model_name="referralrewardaccumulator",
            old_name="event_count",
            new_name="rewarded_posting_count",
        ),
    ]
