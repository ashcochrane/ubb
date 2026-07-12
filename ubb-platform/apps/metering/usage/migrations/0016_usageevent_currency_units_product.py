from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("usage", "0015_add_tenant_effective_index")]
    operations = [
        migrations.AddField(model_name="usageevent", name="units",
                            field=models.BigIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="usageevent", name="currency",
                            field=models.CharField(default="usd", max_length=3)),
        migrations.AddField(model_name="usageevent", name="product_id",
                            field=models.CharField(blank=True, db_index=True, default="", max_length=100)),
    ]
