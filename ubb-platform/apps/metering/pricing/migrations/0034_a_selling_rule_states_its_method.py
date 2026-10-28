"""A selling rule states its pricing method; nothing else states one (R10-W4).

The owner's ruling 4 (2026-10-27): stop encoding `direct_event_price` as a null
whose meaning the resolver inferred.

1. **The backfill.** Every rule in a Pricing Book whose method is null is given
   `direct_event_price` — what resolution already read that null as, so no
   price moves (§0.4 E: economically neutral). A customer override is a
   Pricing Book of its own, so its rules are selling rules and are included.
2. **`ck_rate_a_selling_rule_states_its_method`.** A rule carries a method if
   and only if it sits in a Pricing Book: a cost book's rate, and a row in no
   book, carry null. A cost rate holding a method would be refused here rather
   than rewritten — no route has ever written one, so none is expected; if one
   exists the constraint fails to install and says so.

**No trigger is lifted.** The two on `ubb_rate` fire on an INSERT that names no
declaration (`0020`) and on an UPDATE that moves `valid_from` or `valid_to`
(`0018`); the backfill updates `pricing_method` alone, so neither fires. The
tests pin that both are still installed afterwards.

**The reverse** drops the constraint and leaves the stated methods: under the
old schema a stated `direct_event_price` was legal, and a null and that value
meant the same price, so there is nothing to undo that a reader could see.
"""
from django.db import migrations, models

DIRECT_EVENT_PRICE = "direct_event_price"


def state_the_method(apps, schema_editor):
    Rate = apps.get_model("pricing", "Rate")
    Rate.objects.filter(pricing_book__isnull=False,
                        pricing_method__isnull=True).update(
        pricing_method=DIRECT_EVENT_PRICE)


class Migration(migrations.Migration):

    dependencies = [
        ("pricing", "0033_rules_charges_and_cost_books_are_usd_only"),
    ]

    operations = [
        migrations.RunPython(state_the_method, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="rate",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(pricing_book__isnull=False,
                             pricing_method__isnull=False)
                    | models.Q(pricing_book__isnull=True,
                               pricing_method__isnull=True)),
                name="ck_rate_a_selling_rule_states_its_method"),
        ),
    ]
