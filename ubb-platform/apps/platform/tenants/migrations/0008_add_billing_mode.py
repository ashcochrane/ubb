from django.db import migrations, models


def backfill_billing_mode(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    for tenant in Tenant.objects.all():
        tenant.billing_mode = "prepaid" if "billing" in (tenant.products or []) else "meter_only"
        tenant.save(update_fields=["billing_mode"])


class Migration(migrations.Migration):
    dependencies = [("tenants", "0007_rename_arrears_to_min_balance")]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="billing_mode",
            field=models.CharField(
                choices=[
                    ("meter_only", "Meter only"),
                    ("prepaid", "Prepaid credits"),
                    ("postpaid", "Postpaid"),
                ],
                db_index=True,
                default="meter_only",
                max_length=20,
            ),
        ),
        migrations.RunPython(backfill_billing_mode, migrations.RunPython.noop),
    ]
