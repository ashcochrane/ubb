from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("pricing", "0004_add_markup_composite_index")]

    operations = [
        migrations.DeleteModel(name="ProviderRate"),
    ]
