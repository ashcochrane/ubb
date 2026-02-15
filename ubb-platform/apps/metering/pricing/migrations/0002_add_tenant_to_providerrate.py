import django.db.models.deletion
from django.db import migrations, models


def backfill_tenant(apps, schema_editor):
    ProviderRate = apps.get_model("pricing", "ProviderRate")
    Tenant = apps.get_model("tenants", "Tenant")
    default_tenant = Tenant.objects.first()
    if default_tenant:
        ProviderRate.objects.filter(tenant__isnull=True).update(tenant=default_tenant)


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0001_initial"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        # Step 1: Add nullable FK
        migrations.AddField(
            model_name="providerrate",
            name="tenant",
            field=models.ForeignKey(
                "tenants.Tenant",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="provider_rates",
                null=True,
            ),
        ),
        # Step 2: Backfill existing rows
        migrations.RunPython(backfill_tenant, migrations.RunPython.noop),
        # Step 3: Make non-nullable + add indexes
        migrations.AlterField(
            model_name="providerrate",
            name="tenant",
            field=models.ForeignKey(
                "tenants.Tenant",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="provider_rates",
            ),
        ),
        migrations.AddIndex(
            model_name="providerrate",
            index=models.Index(
                fields=["tenant", "provider", "event_type", "metric_name"],
                name="idx_provrate_tenant_lookup",
            ),
        ),
    ]
