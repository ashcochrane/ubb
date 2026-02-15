from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("usage", "0012_update_invoice_topup_fk_to_topups"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name="Invoice",
                ),
            ],
            database_operations=[],  # Table stays in place
        ),
    ]
