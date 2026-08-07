# The async ingest staging table goes (slice 1, #238). Its producer — the
# published ingest route and the accept pipeline behind it — was deleted two
# commits ago, and this commit deletes the settle sweep that was its only
# consumer, so nothing writes a row and nothing reads one.
#
# WHY ROWS ARE ALLOWED TO GO. ADR-0007 §1 requires a migration that destroys
# data to say so; the pre-squash exemption that covered slice 0's drops is
# spent, so this states it instead. Nothing is deployed — no server, no hosted
# database — so the only rows that can exist are on a developer machine, and
# every one of them is a raw event whose exact price was already settled into
# a durable `UsageEvent` (the settle path's whole job). The `UsageEvent` rows
# ARE the record; a settled raw is a spent staging row, not billing history.
# An UNSETTLED raw on a developer machine would be a lost accept, which is why
# this is cheap now and would not have been after admission.
#
# The two migrations that created and widened this table (0024, 0025) STAY.
# They are historical migrations and the sweep excludes them until slice 8,
# which ends that exclusion by deleting them.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("usage", "0028_remove_usageevent_idx_usage_attribution_and_more"),
    ]

    operations = [
        # The index goes first: Django's own autodetector emits the index
        # removal ahead of the model deletion, and hand-writing them in the
        # other order leaves `makemigrations --check` seeing a difference.
        migrations.RemoveIndex(
            model_name="rawingestevent",
            name="idx_rawingest_claim",
        ),
        migrations.DeleteModel(name="RawIngestEvent"),
    ]
