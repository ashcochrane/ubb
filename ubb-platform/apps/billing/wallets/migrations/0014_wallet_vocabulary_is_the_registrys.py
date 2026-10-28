"""The wallet's own vocabulary is the registry's (R10-W4, ruling 7).

1. **Every stored transaction type moves to the registry's lowercase token.**
   The ledger spelled its eleven types in UPPER_SNAKE, which the registry's
   token rule refuses; the owner ruled the canonical tokens lowercase, with no
   per-concept exception and no dual acceptance afterwards. One `UPDATE` per
   type, so a row whose type is outside the eleven is left exactly as it was —
   and step 3 then refuses to install over it rather than rewriting it.
2. **A credit grant's source `auto_topup` becomes `auto_top_up`.** One concept
   has one spelling (ADR-0006 §2): the webhook catalogue, the audit actions and
   the audit resource types already say `auto_top_up`.
3. **`ck_wallet_transaction_type_known` and `ck_credit_grant_source_known`**
   admit exactly the registry's sets from here on. No trigger guards either
   table (the W6 inventory), so no lift is needed.

**Economically neutral** (§0.4 E): no amount, balance or allocation is read or
written — only the two vocabulary columns' spellings.

**The reverse is exact**: drop both constraints, then move every value back.
"""
from django.db import migrations, models

#: The registry's lowercase token for each spelling the ledger stored. Frozen
#: here, as data, so the migration means the same thing whatever the registry
#: says later.
TRANSACTION_TYPES = {
    "TOP_UP": "top_up",
    "USAGE_DEDUCTION": "usage_deduction",
    "WITHDRAWAL": "withdrawal",
    "REFUND": "refund",
    "ADJUSTMENT": "adjustment",
    "DISPUTE_DEDUCTION": "dispute_deduction",
    "STRIPE_REFUND": "stripe_refund",
    "DEBIT": "debit",
    "GRANT": "grant",
    "GRANT_EXPIRY": "grant_expiry",
    "GRANT_VOID": "grant_void",
}
GRANT_SOURCES = {"auto_topup": "auto_top_up"}

_TYPE_CHOICES = [
    ("top_up", "Top Up"),
    ("usage_deduction", "Usage Deduction"),
    ("withdrawal", "Withdrawal"),
    ("refund", "Refund"),
    ("adjustment", "Adjustment"),
    ("dispute_deduction", "Dispute Deduction"),
    ("stripe_refund", "Stripe Refund"),
    ("debit", "Debit"),
    ("grant", "Credit Grant"),
    ("grant_expiry", "Credit Grant Expiry"),
    ("grant_void", "Credit Grant Void"),
]
_SOURCE_CHOICES = [
    ("checkout", "Checkout"),
    ("auto_top_up", "Auto Top-Up"),
    ("api", "API"),
    ("other", "Other"),
]


def _move(apps, mapping, model_name, field):
    model = apps.get_model("wallets", model_name)
    for old, new in mapping.items():
        model.objects.filter(**{field: old}).update(**{field: new})


def forwards(apps, schema_editor):
    _move(apps, TRANSACTION_TYPES, "WalletTransaction", "transaction_type")
    _move(apps, GRANT_SOURCES, "CreditGrant", "source")


def backwards(apps, schema_editor):
    _move(apps, {new: old for old, new in TRANSACTION_TYPES.items()},
          "WalletTransaction", "transaction_type")
    _move(apps, {new: old for old, new in GRANT_SOURCES.items()},
          "CreditGrant", "source")


class Migration(migrations.Migration):

    dependencies = [
        ("wallets", "0013_a_wallet_movement_states_its_reason"),
    ]

    operations = [
        migrations.AlterField(
            model_name="wallettransaction",
            name="transaction_type",
            field=models.CharField(choices=_TYPE_CHOICES, db_index=True,
                                   max_length=20),
        ),
        migrations.AlterField(
            model_name="creditgrant",
            name="source",
            field=models.CharField(choices=_SOURCE_CHOICES, default="other",
                                   max_length=20),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.AddConstraint(
            model_name="wallettransaction",
            constraint=models.CheckConstraint(
                condition=models.Q(transaction_type__in=sorted(
                    TRANSACTION_TYPES.values())),
                name="ck_wallet_transaction_type_known"),
        ),
        migrations.AddConstraint(
            model_name="creditgrant",
            constraint=models.CheckConstraint(
                condition=models.Q(source__in=sorted(
                    ["api", "auto_top_up", "checkout", "other"])),
                name="ck_credit_grant_source_known"),
        ),
    ]
