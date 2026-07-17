# #42 (spec §G): enforcement mode becomes two-position — `advisory` retired.
# Advisory promised "never act"; `off` is the honest nearest state (and no
# advisory tenant exists in prod). The data map runs before the choices
# narrow so no row is ever stranded on a retired value.
from django.db import migrations, models


def advisory_to_off(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    Tenant.objects.filter(enforcement_mode="advisory").update(enforcement_mode="off")


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0018_the_clean_cut_run_to_task"),
    ]

    operations = [
        migrations.RunPython(advisory_to_off, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="tenant",
            name="enforcement_mode",
            field=models.CharField(
                choices=[("off", "Off"), ("enforcing", "Enforcing")],
                db_index=True,
                default="off",
                max_length=10,
            ),
        ),
    ]
