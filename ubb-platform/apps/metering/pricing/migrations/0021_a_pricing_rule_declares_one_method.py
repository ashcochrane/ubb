"""A pricing rule declares one method, and never composes (#355, #147 §2).

**The column.** How a rule derives a customer price — a margin over what UBB
knows the call cost, or an amount attached directly to the event — as one of the
two values the registry ratified (`domain-vocabulary/concepts/economics.yaml`,
`pricing_method`). The members are taken from the generated frozenset rather than
typed here, so this table cannot hold a set the agreed model disagrees with.

**NULLABLE, AND NULL IS NOT A THIRD METHOD.** It says the price was not DERIVED
— because it was agreed, or because there is none — and which of those is read
off the price status beside the amount on the posting, which already carries
`waived`, `unknown` and `not_applicable`. A fourth enum value meaning "there
wasn't one" would say the same thing twice and give two fields a chance to
disagree. The pricing-versions decision's receipt shape lists four values; the
ratified concept has two and ADR-0008 §2 makes the registry the oracle.

**Every existing row is null, and that is the reading rather than a backfill left
undone.** No rate has ever carried a method: the engine decides one from the rung
that supplied a price and writes it into the receipt. So there is no value this
migration could invent for an existing row that would be true of it, and `null`
— *this rule states no method* — is exactly what each one means.

**TWO CHECKS, AND THEY ARE NOT ONE RULE SAID TWICE.**

`ck_rate_pricing_method` keeps the value set closed at the table. `choices=`
reaches forms, the admin and `full_clean`, and none of those is enforcement:
`QuerySet.update()` and raw SQL go straight past them (ADR-0007 §2). NULL is
admitted because NULL is not a value — the membership test answers NULL for it,
which a check reads as satisfied, and the disjunction says so out loud rather
than leaving a reader to wonder whether the admission was noticed.

`ck_rate_never_composes` is the non-composition property, and it is a statement
about the SHAPE of a row rather than about how the row arrived — which is why a
check is the right mechanism here and was not for `0020`'s rule. A rule declaring
`margin_over_cost` may not also carry the per-unit rate or the flat addend beside
it: those are the other method's terms, and a margin with a second component
added to it makes a resolved price impossible to explain by naming ONE rule,
because the middle term of the chain is nowhere on the record. ⚠ **One direction
only, deliberately.** The mirrored refusal — a direct rule carrying a margin term
— is not expressible on this table, because no percentage column exists on it
while markup is still a separate record. The ticket that moves markup onto the
rule is the ticket that adds the other half.

**No existing row can fail either check.** Every rate is null-methoded, and both
conditions are satisfied by a NULL method whatever else the row carries.

**The refusals are `IntegrityError`, which is what five other mechanisms on this
table already raise** — the partial unique index, `ck_rate_names_one_quantity`,
the declaration reference's own foreign key, `0018`'s transition trigger and
`0020`'s insert trigger. "The write was rejected" is therefore evidence of
nothing here; every test of these two asserts the constraint's NAME, and each
test class says which of the two it is about rather than sharing a default.

**The reverse is real.** Dropping both checks and the column returns the table to
what `0020` left. Nothing has to be unpicked: no row is written and no column's
meaning changes.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0014_customer_suspension_reason'),
        ('event_types', '0006_reported_cost_mapping'),
        ('pricing', '0020_a_new_rate_names_a_declaration_or_is_refused'),
        ('tenants', '0024_remove_tenant_require_cost_card_coverage'),
    ]

    operations = [
        migrations.AddField(
            model_name='rate',
            name='pricing_method',
            field=models.CharField(blank=True, choices=[('direct_event_price', 'direct_event_price'), ('margin_over_cost', 'margin_over_cost')], max_length=32, null=True),
        ),
        migrations.AddConstraint(
            model_name='rate',
            constraint=models.CheckConstraint(condition=models.Q(('pricing_method__isnull', True), ('pricing_method__in', ['direct_event_price', 'margin_over_cost']), _connector='OR'), name='ck_rate_pricing_method'),
        ),
        migrations.AddConstraint(
            model_name='rate',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('pricing_method', 'margin_over_cost'), _negated=True), models.Q(('fixed_micros', 0), ('rate_per_unit_micros', 0)), _connector='OR'), name='ck_rate_never_composes'),
        ),
    ]
