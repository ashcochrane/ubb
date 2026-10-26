"""A price held on a name states its reason (#473 row 4, as ruled; the
consultant's review of #618).

A posting held on a name — an Event Type with no production declaration, or a
quantity its publication does not carry — prices `unknown`, never `known` and
never `waived`. Ruled as `unknown` WITH A STATED REASON, mirroring ADR-0020, so
the price status's own reason gains the held name's cause: `event_type_not_
declared` and `measurement_not_declared`, the same tokens its cost reason
already carries. The choices move with the registry, and the column's closed
set at the database moves with them.

The set's check is dropped and re-added rather than altered, because a `CHECK`
has no `ALTER`; nothing in the table can fail the new one, since it admits two
values more than the old one and nothing has written either yet. The rule that
ties the reason to the status (`ck_posting_pricing_status_agrees_with_the_
price`) lets `unknown` carry any reason and names no value, and the trigger
holding the pair (`0046`, widened by `0049`) is untouched: the reason is written
once with an `unknown` posting and cleared by the resolution that completes it,
exactly as `negative_price_unsupported` would be.

**The literals are frozen**, for the reason `0036` gives at length. The reverse
restores `0046`'s set, which refuses — as it should — a table holding a row the
older set never admitted.
"""
from django.db import migrations, models

PRICING_STATUS_REASON = [
    ("event_type_not_declared", "event_type_not_declared"),
    ("measurement_not_declared", "measurement_not_declared"),
    ("negative_price_unsupported", "negative_price_unsupported"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("usage", "0049_a_customer_price_becomes_known_only_through_its_door"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="posting",
            name="ck_posting_pricing_status_reason",
        ),
        migrations.AlterField(
            model_name="posting",
            name="pricing_status_reason",
            field=models.CharField(blank=True, choices=PRICING_STATUS_REASON,
                                   max_length=32, null=True),
        ),
        migrations.AddConstraint(
            model_name="posting",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("pricing_status_reason__isnull", True),
                    ("pricing_status_reason__in",
                     [value for value, _ in PRICING_STATUS_REASON]),
                    _connector="OR",
                ),
                name="ck_posting_pricing_status_reason",
            ),
        ),
    ]
