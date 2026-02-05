from django.db import connection, migrations


def create_gin_index(apps, schema_editor):
    if connection.vendor == 'postgresql':
        schema_editor.execute(
            'CREATE INDEX IF NOT EXISTS idx_usage_event_group_keys '
            'ON ubb_usage_event USING GIN (group_keys jsonb_path_ops);'
        )


def drop_gin_index(apps, schema_editor):
    if connection.vendor == 'postgresql':
        schema_editor.execute('DROP INDEX IF EXISTS idx_usage_event_group_keys;')


class Migration(migrations.Migration):
    dependencies = [
        ("usage", "0010_usageevent_group_keys"),
    ]

    operations = [
        migrations.RunPython(create_gin_index, drop_gin_index),
    ]
