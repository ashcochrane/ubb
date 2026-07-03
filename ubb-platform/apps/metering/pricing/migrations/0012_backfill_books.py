from django.db import migrations

from apps.metering.pricing.migrations import _book_backfill


class Migration(migrations.Migration):
    dependencies = [("pricing", "0011_ratecard_container")]
    operations = [
        migrations.RunPython(_book_backfill.forwards, _book_backfill.backwards),
    ]
