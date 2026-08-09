# #246: the switch takes the name of what it actually governs.
#
# It was named for the arrival-time lane. Slice 1 (#192) deleted that lane and
# kept the switch, because it never was the lane's switch — it gates real-time
# maintenance of the live spend counters (the synchronous debit and its
# crossing check, both reconciles' counter legs, and the upward repair).
#
# RenameField, never AddField + RemoveField (ADR-0007 §1): a rename carries its
# data, and every tenant that had deliberately opted out keeps that posture.
# Postgres does this as an ALTER TABLE ... RENAME COLUMN — no table rewrite, no
# default backfill, and reversible.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0022_tenantapikey_role"),
    ]

    operations = [
        migrations.RenameField(
            model_name="tenant",
            old_name="arrival_signals_enabled",
            new_name="live_counter_maintenance_enabled",
        ),
    ]
