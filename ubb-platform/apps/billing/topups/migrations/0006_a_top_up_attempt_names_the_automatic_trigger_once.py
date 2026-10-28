"""A top-up attempt names the automatic trigger once (R10-W4, the owner's review).

The automatic top-up is one product concept, spelled `auto_top_up` everywhere
UBB names it: the route, `AutoTopUpConfig`, the credit grant's source
(`wallets/0014`), the `auto_top_up.requires_action` webhook and the
`auto_top_up.configured` audit action. A top-up attempt's trigger was the last
stored value still spelled run-together. Pre-launch: no alias, no dual
acceptance — the value moves, and the old spelling is retired.

1. **The one-pending constraint is dropped first**, because its condition names
   the old value; it comes back in step 4 naming the new one, under the
   canonical name `uq_one_pending_auto_top_up_per_customer`.
2. **The trigger's choices** admit `auto_top_up` in place of the old token.
3. **Every stored row moves.** One `UPDATE`; a row with any other trigger is
   left exactly as it was. The old constraint held at most one pending
   automatic attempt per customer and no row carried the new spelling before
   this step, so the moved rows satisfy step 4 by construction.
4. **The constraint is recreated** over the new value.

**Economically neutral** (§0.4 E): no amount, status or balance is read or
written — only the trigger's spelling.

**The reverse is exact**: drop the new constraint, move every value back,
restore the old choices and the old constraint.
"""
from django.db import migrations, models

#: The old spelling → the canonical one. Frozen here, as data, so the
#: migration means the same thing whatever the model says later.
TRIGGERS = {"auto_topup": "auto_top_up"}

_OLD_CONSTRAINT = "uq_one_pending_auto_topup_per_customer"
_NEW_CONSTRAINT = "uq_one_pending_auto_top_up_per_customer"

_TRIGGER_CHOICES = [
    ("manual", "Manual"),
    ("auto_top_up", "Auto Top-Up"),
    ("widget", "Widget"),
]


def _move(apps, mapping):
    TopUpAttempt = apps.get_model("topups", "TopUpAttempt")
    for old, new in mapping.items():
        TopUpAttempt.objects.filter(trigger=old).update(trigger=new)


def forwards(apps, schema_editor):
    _move(apps, TRIGGERS)


def backwards(apps, schema_editor):
    _move(apps, {new: old for old, new in TRIGGERS.items()})


class Migration(migrations.Migration):

    dependencies = [
        ("topups", "0005_topupattempt_billing_owner_id"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="topupattempt",
            name=_OLD_CONSTRAINT,
        ),
        migrations.AlterField(
            model_name="topupattempt",
            name="trigger",
            field=models.CharField(choices=_TRIGGER_CHOICES, max_length=20),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.AddConstraint(
            model_name="topupattempt",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="pending", trigger="auto_top_up"),
                fields=("customer",),
                name=_NEW_CONSTRAINT,
            ),
        ),
    ]
