# The arrival-signals switch (#46, delivery spec §E): default ON for every
# tenant, including tenant one — prepaid, 100+ events/s, async is the exact
# profile the fast trigger was built for, and the ≤5s p99 signal SLO presumes
# ON. OFF is the honest settle-latency posture, never a contract change.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0019_two_position_enforcement_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="arrival_signals_enabled",
            field=models.BooleanField(default=True),
        ),
    ]
