# The app label moved 'tasks' -> 'work' (#196, slice 0 §9).
#
# 0001-0011 carry `replaces` so an existing database resolves them to "already
# applied" and runs no SQL. That is exactly what preserves the tables — but it
# also means nothing in that chain executes on the databases that need fixing.
# django_content_type still holds rows under the retired label, and post_migrate
# would add a second row per model under the new one, leaving every admin log
# entry and permission attached to the stale pair.
#
# So this leaf carries no `replaces`: it runs on every database. On a fresh one
# there is nothing under the old label and it is a no-op; on a populated one it
# re-labels the existing rows in place, which keeps their primary keys and so
# keeps everything pointing at them intact. No schema is touched either way.

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

OLD_LABEL = "tasks"
NEW_LABEL = "work"


def _relabel(apps, *, source, target):
    ContentType = apps.get_model("contenttypes", "ContentType")

    stale = ContentType.objects.filter(app_label=source)
    # A row already under the target label means some earlier run created it.
    # Re-labelling onto it would break (app_label, model) uniqueness, so leave
    # that pair alone and move only the ones with a free destination.
    taken = set(
        ContentType.objects.filter(
            app_label=target, model__in=stale.values_list("model", flat=True)
        ).values_list("model", flat=True)
    )
    if taken:
        # Skipping is the safe choice, but it is also the case this migration
        # exists to prevent: the rows left behind keep whatever admin log
        # entries and permissions point at them, now orphaned. Say so, because
        # a silent skip reads exactly like a successful one.
        logger.warning(
            "content types %s already exist under %r, so the %r rows for them "
            "stay put; admin log entries and permissions still reference those",
            sorted(taken), target, source,
        )
    stale.exclude(model__in=taken).update(app_label=target)


def forwards(apps, schema_editor):
    _relabel(apps, source=OLD_LABEL, target=NEW_LABEL)


def backwards(apps, schema_editor):
    _relabel(apps, source=NEW_LABEL, target=OLD_LABEL)


class Migration(migrations.Migration):

    dependencies = [
        ("work", "0011_remove_task_floor_snapshot_micros"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
