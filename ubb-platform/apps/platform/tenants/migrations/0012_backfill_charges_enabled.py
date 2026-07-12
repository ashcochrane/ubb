from django.db import migrations


def _backfill(apps, schema_editor):
    # Existing tenants with a connected account were already charge-ready before
    # charges_enabled existed; mark them so the new charge-gate doesn't skip them.
    schema_editor.execute(
        "UPDATE ubb_tenant SET charges_enabled = TRUE "
        "WHERE stripe_connected_account_id IS NOT NULL AND stripe_connected_account_id != ''")


class Migration(migrations.Migration):
    dependencies = [("tenants", "0011_tenant_charges_enabled_connectoauthstate")]
    operations = [migrations.RunPython(_backfill, migrations.RunPython.noop)]
