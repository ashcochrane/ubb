from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wallets", "0008_wallettransaction_actor_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="customerbillingprofile",
            name="soft_min_balance_micros",
            field=models.BigIntegerField(blank=True, null=True),
        ),
    ]
