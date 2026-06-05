from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("tenants", "0008_add_billing_mode")]
    operations = [
        migrations.AddField(
            model_name="tenant",
            name="default_currency",
            field=models.CharField(default="usd", max_length=3),
        ),
    ]
