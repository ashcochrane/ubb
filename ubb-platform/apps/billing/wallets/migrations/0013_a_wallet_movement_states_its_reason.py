"""A wallet movement states its REASON, under its own name (#479).

The ledger column categorising a manual credit or debit was `reason_code` —
the stop cause's public name, which is a different concept (why work was
stopped, not why money moved), and ADR-0006 §2 does not let two concepts share
one. The ruling renames it `movement_reason` and declares its six values as
the registry's closed `movement_reason`.

1. **`RenameField`** (ADR-0007 §1): the column and its index move with every
   stored value intact. Nothing is rewritten.
2. **`ck_wallet_transaction_movement_reason_known`** holds the registry's set,
   or the empty string an automated movement records. The route has refused
   anything else by hand since Phase 1, so no stored row is outside it; if one
   were, this step would fail rather than rewrite it.

**The reverse is exact**: drop the constraint, rename the column back.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wallets", "0012_wallet_money_is_usd_only"),
    ]

    operations = [
        migrations.RenameField(
            model_name="wallettransaction",
            old_name="reason_code",
            new_name="movement_reason",
        ),
        migrations.AddConstraint(
            model_name="wallettransaction",
            constraint=models.CheckConstraint(
                condition=models.Q(movement_reason="")
                | models.Q(movement_reason__in=[
                    "chargeback", "correction", "goodwill", "migration",
                    "other", "write_off"]),
                name="ck_wallet_transaction_movement_reason_known"),
        ),
    ]
