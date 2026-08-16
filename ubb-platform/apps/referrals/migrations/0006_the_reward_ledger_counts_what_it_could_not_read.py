"""A reward period records how many costs it had to work around (#328).

`ReferralRewardLedger.raw_cost_micros` is the tenant's own cost over the period,
added up event by event from postings whose supplier cost may be unresolved
(#317). The reconciler already skipped those deliberately — a profit share over
a cost UBB has not learned falls back to the estimate — but nothing said how
often it happened, so a period reconciled entirely from estimates was written
down exactly like one reconciled from figures. `calculation_method` cannot say
it either: it names ONE method for the whole period.

Every existing row gets zero, which is what those rows can honestly claim: no
reconciliation before this commit counted anything, and the ledger is an
immutable log — the numbers in it were true when written.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("referrals", "0005_auto_hardening"),
    ]

    operations = [
        migrations.AddField(
            model_name="referralrewardledger",
            name="unresolved_event_count",
            field=models.IntegerField(default=0),
        ),
    ]
