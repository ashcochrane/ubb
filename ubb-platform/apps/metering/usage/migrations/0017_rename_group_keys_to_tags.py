from django.db import connection, migrations


def swap_gin_index(apps, schema_editor):
    if connection.vendor == "postgresql":
        schema_editor.execute("DROP INDEX IF EXISTS idx_usage_event_group_keys;")
        schema_editor.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_event_tags "
            "ON ubb_usage_event USING GIN (tags jsonb_path_ops);"
        )


def unswap_gin_index(apps, schema_editor):
    if connection.vendor == "postgresql":
        schema_editor.execute("DROP INDEX IF EXISTS idx_usage_event_tags;")
        schema_editor.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_event_group_keys "
            "ON ubb_usage_event USING GIN (group_keys jsonb_path_ops);"
        )


class Migration(migrations.Migration):
    dependencies = [("usage", "0016_usageevent_currency_units_product")]
    operations = [
        migrations.RenameField(model_name="usageevent", old_name="group_keys", new_name="tags"),
        migrations.RunPython(swap_gin_index, unswap_gin_index),
    ]
