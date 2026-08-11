"""The posting's measured quantities move to a child record of their own (#270).

The three operations are ordered so that the column is only dropped once its
contents are somewhere else. ADR-0007 §1 — *a migration that renames or moves a
column carries its data* — is what the middle operation is for: an autodetected
``RemoveField`` beside a ``CreateModel`` is an add-plus-remove that empties what
it claims to move, and Django emits them in exactly that order if you let it.

The reverse carries the data back the same way, and is exercised against a real
database in ``tests/test_posting_measurement.py`` rather than being asserted to
exist. A reverse nobody has run is a ``noop`` with better manners.
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

    ``QuerySet.update`` rather than ``save()``: the posting's own save guard
    refuses any non-adding write, and a historical model would not carry it
    anyway. Reversing a move must not be the one path that loses the data.
    """
    Posting = apps.get_model("usage", "Posting")
    PostingMeasurement = apps.get_model("usage", "PostingMeasurement")
    for measurement in PostingMeasurement.objects.iterator(chunk_size=1000):
        Posting.objects.filter(pk=measurement.posting_id).update(
            usage_metrics=measurement.usage_metrics)
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
