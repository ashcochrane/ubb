import secrets
from django.db import migrations


def backfill_widget_secrets(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    for tenant in Tenant.objects.filter(widget_secret=""):
        tenant.widget_secret = secrets.token_urlsafe(48)
        tenant.save(update_fields=["widget_secret"])


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0002_tenant_widget_secret"),
    ]

    operations = [
        migrations.RunPython(backfill_widget_secrets, migrations.RunPython.noop),
    ]
