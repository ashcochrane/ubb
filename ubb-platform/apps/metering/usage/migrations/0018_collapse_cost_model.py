from django.db import migrations, models


def backfill(apps, schema_editor):
    UsageEvent = apps.get_model("usage", "UsageEvent")
    UsageEvent.objects.filter(provider_cost_micros__isnull=True).update(provider_cost_micros=0)
    from django.db.models import F
    UsageEvent.objects.filter(billed_cost_micros__isnull=True).update(billed_cost_micros=F("cost_micros"))


class Migration(migrations.Migration):
    dependencies = [("usage", "0017_rename_group_keys_to_tags")]
    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.AlterField(model_name="usageevent", name="provider_cost_micros",
                              field=models.BigIntegerField(default=0)),
        migrations.AlterField(model_name="usageevent", name="billed_cost_micros",
                              field=models.BigIntegerField(default=0)),
        migrations.RemoveField(model_name="usageevent", name="cost_micros"),
        migrations.RemoveField(model_name="usageevent", name="usage_metrics"),
        migrations.RemoveField(model_name="usageevent", name="properties"),
    ]
