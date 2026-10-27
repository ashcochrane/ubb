"""A billing period's count takes the name it is published under (R10-W4).

`TenantBillingPeriod`'s count of every metered usage event recorded in the
period, priced or not and never a Task Charge (#563), was already published as
`recorded_events`, the registry's `analytics_measure`, while the column kept an
older internal name. Ruling 1 of R10-W4 retires that name everywhere living, so
the column takes the published one and a reader meets one name for one count.

One operation, `RenameField` (ADR-0007 §1): the column moves with every stored
value intact, and the reverse is exact.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_billing", "0014_a_billing_period_names_what_it_sums"),
    ]

    operations = [
        migrations.RenameField(
            model_name="tenantbillingperiod",
            old_name="event_count",
            new_name="recorded_events",
        ),
    ]
