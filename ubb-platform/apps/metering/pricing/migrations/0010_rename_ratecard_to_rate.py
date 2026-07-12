from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0009_alter_ratecard_pricing_model_pricingperiodcounter"),
    ]

    # State-only: the table stays `ubb_rate_card`, so Django's model state must
    # rename WITHOUT touching the database. RenameModel would otherwise attempt a
    # table rename; db_table is pinned, but we wrap in SeparateDatabaseAndState to
    # be explicit and future-proof.
    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameModel(old_name="RateCard", new_name="Rate"),
            ],
            database_operations=[],
        ),
    ]
