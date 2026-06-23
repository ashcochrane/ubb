"""Flip webhook event_types from "empty = all" to explicit opt-in.

Old semantics: an empty event_types list meant "deliver every event".
New semantics: [] means "deliver nothing"; ["*"] means "deliver all".

Existing configs that relied on the implicit-all default ([]) are backfilled
to ["*"] so their delivery behavior is unchanged across the deploy. This must
ship in the same release as the new fan-out code (apps/platform/events/webhooks.py).
"""
from django.db import migrations, models


def backfill_empty_event_types(apps, schema_editor):
    """Preserve old "all events" behavior for configs created before the flip."""
    TenantWebhookConfig = apps.get_model("events", "TenantWebhookConfig")
    TenantWebhookConfig.objects.filter(event_types=[]).update(event_types=["*"])


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0002_tenantwebhookconfig_webhookdeliveryattempt"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tenantwebhookconfig",
            name="event_types",
            field=models.JSONField(
                default=list,
                help_text='Event types to deliver: ["*"] = all, [] = none, or specific types like ["usage.recorded"].',
            ),
        ),
        # Reverse is a no-op: a backfilled ["*"] is indistinguishable from a
        # user-set ["*"], so we cannot safely restore the original [].
        migrations.RunPython(backfill_empty_event_types, migrations.RunPython.noop),
    ]
