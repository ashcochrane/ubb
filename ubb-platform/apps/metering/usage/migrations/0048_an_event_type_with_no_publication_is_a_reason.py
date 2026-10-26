"""An Event Type with no production declaration is a reason a cost is unresolved
(#568, #193 §B5).

The registry's closed `unresolved_reason` gains `event_type_not_declared`: an
event naming an Event Type nobody declared, or one declared and never published
(#605), is recorded with no cost and no price and its name held, and this is the
value the posting's column says. The choices move with the registry, and the
column's closed set at the database moves with them.

The set's check is dropped and re-added rather than altered, because a `CHECK`
has no `ALTER`; nothing in the table can fail the new one, since it admits one
value more than the old one and nothing has written that value yet. The rule
that ties the reason to the status (`ck_posting_costing_status_agrees_with_the_
cost`) names no value and is untouched, and so is the trigger holding the pair
(`0037`): the new reason is written once with an `unresolved` posting and
cleared by the settlement that resolves it, exactly as its siblings are.

**The literals are frozen**, for the reason `0036` gives at length: a migration
records the schema as it was on the day it ran. The reverse restores `0036`'s
set, which refuses — as it should — a table holding a row the older set never
admitted.
"""
from django.db import migrations, models

UNRESOLVED_REASON = [
    ("cost_rate_missing", "cost_rate_missing"),
    ("event_type_not_declared", "event_type_not_declared"),
    ("measurement_not_declared", "measurement_not_declared"),
    ("reported_cost_missing", "reported_cost_missing"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("usage", "0047_the_regime_decides_why_a_price_does_not_apply"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="posting",
            name="ck_posting_unresolved_reason",
        ),
        migrations.AlterField(
            model_name="posting",
            name="unresolved_reason",
            field=models.CharField(blank=True, choices=UNRESOLVED_REASON,
                                   max_length=32, null=True),
        ),
        migrations.AddConstraint(
            model_name="posting",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("unresolved_reason__isnull", True),
                    ("unresolved_reason__in",
                     ["cost_rate_missing", "event_type_not_declared",
                      "measurement_not_declared", "reported_cost_missing"]),
                    _connector="OR",
                ),
                name="ck_posting_unresolved_reason",
            ),
        ),
    ]
