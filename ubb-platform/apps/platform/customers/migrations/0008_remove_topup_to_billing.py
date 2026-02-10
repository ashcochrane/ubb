from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0007_remove_wallet_to_billing"),
        ("topups", "0001_initial"),
        ("usage", "0012_update_invoice_topup_fk_to_topups"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="TopUpAttempt"),
                migrations.DeleteModel(name="AutoTopUpConfig"),
            ],
            database_operations=[],
        ),
    ]
