from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_billing", "0008_the_clean_cut_run_to_task"),
    ]

    operations = [
        migrations.AddField(
            model_name="billingtenantconfig",
            name="soft_min_balance_micros",
            field=models.BigIntegerField(blank=True, null=True),
        ),
    ]
