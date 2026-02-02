from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0001_initial"),
        ("usage", "0008_clear_orphan_invoices"),
    ]

    operations = [
        migrations.AlterField(
            model_name="invoice",
            name="top_up_attempt",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="invoice",
                to="customers.topupattempt",
            ),
        ),
    ]
