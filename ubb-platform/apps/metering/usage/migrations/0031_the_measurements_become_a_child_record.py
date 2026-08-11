"""The posting's measured quantities move to a child record of their own (#270).

The three operations are ordered so that the column is only dropped once its
contents are somewhere else. ADR-0007 §1 — *a migration that renames or moves a
column carries its data* — is what the middle operation is for: an autodetected
``RemoveField`` beside a ``CreateModel`` is an add-plus-remove that empties what
it claims to move, and Django emits them in exactly that order if you let it.

The reverse carries the data back the same way, and is exercised against a real
database in ``tests/test_posting_measurement.py`` rather than being asserted to
exist. A reverse nobody has run is a ``noop`` with better manners.

**EVERY POSTING THE FOLD SEES GETS A CHILD, AND THAT IS NOT THE EMPTY RECORD THE
SPLIT FORBIDS.** The rule is that a *synthetic charge* posting — a Task sold at
one agreed price — has no measurement record, so that absence is expressed by
absence. No such posting exists: the `kind` discriminator is a declared concept
in `core/vocabulary.py` and not yet a column, and nothing in this repository
projects a Charge into a posting. Every row this migration can see is therefore
a metered one, whose child is correct, and `{}` is what those rows already
stored inline.

Skipping rows with an empty bag would be the wrong repair: it would invent a
discriminator out of "the caller sent no quantities", which is a different fact
and one the split exists to keep separable. **The slice that adds `kind` owns
whatever backfill its own rows need** — recorded here rather than left for
someone to rediscover from the absence of a filter.
"""

import uuid

import django.db.models.deletion
from django.db import migrations, models


def fold_the_measurements_into_the_child(apps, schema_editor):
    """Every posting gets its measurement record, carrying its own bag.

    ``recorded_at`` takes the moment the posting ARRIVED (``created_at``), not
    the moment this migration runs — the quantities were recorded then, and the
    child's own ``created_at`` is what answers "when was this row written".
    """
    Posting = apps.get_model("usage", "Posting")
    PostingMeasurement = apps.get_model("usage", "PostingMeasurement")
    rows = Posting.objects.values_list(
        "id", "usage_metrics", "created_at").iterator(chunk_size=1000)
    PostingMeasurement.objects.bulk_create(
        (PostingMeasurement(posting_id=posting_id,
                            usage_metrics=usage_metrics or {},
                            recorded_at=created_at)
         for posting_id, usage_metrics, created_at in rows),
        batch_size=1000,
    )


def unfold_the_measurements_onto_the_posting(apps, schema_editor):
    """The bags go back inline, and the child records go away.

    ``bulk_update`` rather than ``save()``: the posting's own save guard refuses
    any non-adding write, and a historical model would not carry it anyway.
    Batched rather than row-at-a-time because this is the highest-volume table
    in the system — one statement per thousand rows, not one per row.
    Reversing a move must not be the one path that loses the data.
    """
    Posting = apps.get_model("usage", "Posting")
    PostingMeasurement = apps.get_model("usage", "PostingMeasurement")
    batch = []
    for measurement in PostingMeasurement.objects.iterator(chunk_size=1000):
        batch.append(Posting(pk=measurement.posting_id,
                             usage_metrics=measurement.usage_metrics))
        if len(batch) == 1000:
            Posting.objects.bulk_update(batch, ["usage_metrics"])
            batch = []
    if batch:
        Posting.objects.bulk_update(batch, ["usage_metrics"])
    PostingMeasurement.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('usage', '0030_the_usage_row_becomes_the_posting'),
    ]

    operations = [
        migrations.CreateModel(
            name='PostingMeasurement',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('usage_metrics', models.JSONField(blank=True, default=dict)),
                ('recorded_at', models.DateTimeField()),
                ('prunable_at', models.DateTimeField(blank=True, null=True)),
                ('posting', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='measurement', to='usage.posting')),
            ],
            options={
                'db_table': 'ubb_posting_measurement',
            },
        ),
        migrations.RunPython(fold_the_measurements_into_the_child,
                             unfold_the_measurements_onto_the_posting),
        migrations.RemoveField(
            model_name='posting',
            name='usage_metrics',
        ),
    ]
