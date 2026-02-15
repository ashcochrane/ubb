from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0006_remove_customer_email"),
        ("wallets", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="WalletTransaction"),
                migrations.DeleteModel(name="Wallet"),
            ],
            database_operations=[],
        ),
    ]
