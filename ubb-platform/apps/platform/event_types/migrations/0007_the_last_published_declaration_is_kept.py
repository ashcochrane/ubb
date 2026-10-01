"""An Event Type keeps what its current publication said (#573).

One nullable column, written by `EventType.publish` from here on. This file
exists as more than an `AddField` because of the rows that are published
ALREADY.

**A row published today still holds the declaration it pinned** — a revision is
what would have returned it to draft, and none has happened — so its copy can
be composed from the rows as they stand, and is. Leaving it empty instead would
strand those declarations: publishing an unchanged published declaration moves
nothing, by design, so no later act would ever fill the copy in.

**A row in draft that was published once is NOT filled in, and cannot be.** Its
published content was overwritten in place by the revision — the loss this
column exists to end — and composing a copy from the draft would label an
unpublished declaration as the published one. It stays empty and reads as
nothing published until the tenant publishes again, which is also the only
honest way to get the content back.

The field names below are spelled out rather than read off the models'
`PINNED`: a migration describes the tree as it was on the day it was written,
and one that followed a tuple a later change grows would backfill a different
shape depending on when it ran.

The reverse drops the column and with it every copy. Nothing else was written,
so there is nothing else to unpick.
"""
from django.db import migrations, models

EVENT_TYPE_PINNED = ("key", "costing_method", "source_shape_id",
                     "source_shape_label")
MEASUREMENT_PINNED = ("code", "value_type", "unit", "required_for_costing",
                      "source_kind", "source_path")
MAPPING_PINNED = ("source_kind", "source_path", "amount_representation",
                  "currency", "currency_path")


def keep_what_is_published_now(apps, schema_editor):
    EventType = apps.get_model("event_types", "EventType")
    Measurement = apps.get_model("event_types", "Measurement")
    ReportedCostMapping = apps.get_model("event_types", "ReportedCostMapping")

    published = EventType.objects.filter(declaration_status="published",
                                         published_declaration__isnull=True)
    for event_type in published.iterator():
        measurements = (Measurement.objects.filter(event_type_id=event_type.pk)
                        .order_by("code").values(*MEASUREMENT_PINNED))
        mapping = (ReportedCostMapping.objects
                   .filter(event_type_id=event_type.pk)
                   .values(*MAPPING_PINNED).first())
        pinned = {name: getattr(event_type, name)
                  for name in EVENT_TYPE_PINNED}
        pinned["measurements"] = list(measurements)
        pinned["reported_cost_mapping"] = mapping
        # `update`, so the row's own `updated_at` does not claim an edit the
        # tenant never made.
        (EventType.objects.filter(pk=event_type.pk)
         .update(published_declaration=pinned))


class Migration(migrations.Migration):

    dependencies = [
        ('event_types', '0006_reported_cost_mapping'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventtype',
            name='published_declaration',
            field=models.JSONField(blank=True, default=None, null=True),
        ),
        migrations.RunPython(keep_what_is_published_now,
                             migrations.RunPython.noop),
    ]
