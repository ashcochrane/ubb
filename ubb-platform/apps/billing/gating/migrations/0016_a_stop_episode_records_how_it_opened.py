"""A stop episode records how it opened (#569).

Three nullable columns on the signal ledger: the mechanism that applied the
stop, the bound the line was measured against at the crossing, and the amount
measured then. The winning stop transition stamps them beside `control_id`,
and every recording acknowledgement that names the episode reads them back.

Nothing is backfilled. UBB is not deployed anywhere, so no open episode holds
facts nobody stamped; a row opened before this migration reads null, which is
what an acknowledgement says of a figure it does not have — never 0.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gating", "0015_the_rate_bound_leaves_the_risk_row_for_the_tenant"),
    ]

    operations = [
        migrations.AddField(
            model_name="stopsignalstate",
            name="trigger_source",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="stopsignalstate",
            name="stop_bound_micros",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="stopsignalstate",
            name="stop_measured_micros",
            field=models.BigIntegerField(blank=True, null=True),
        ),
    ]
