"""The tenant declares its default markup rung, explicitly (#357, #147 §5.1).

**The table.** The last rung of the price ladder: where the books in play hold
no rule for a quantity, the customer's price is a percentage over what UBB
knows the call cost. One row per tenant, holding one term.

**A NEW TABLE RATHER THAN A COLUMN ON THE RECORD IT REPLACES.** The tenant
default is the `customer IS NULL` row of `ubb_tenant_markup` today — a rung read
out of an ABSENCE, in a table whose other rows are per-customer overrides. The
replacement is the rung DECLARED, which is what lets declaring it and
withdrawing it be two audit actions rather than one upsert of a row that may or
may not have been there. #369 deletes the record this replaces, together with
the plan catalog's two markup columns, and this table has to exist and resolve
before that can happen.

**`markup_micro_percent`, NOT THE MONEY SUFFIX.** Millionths of a percent —
1_000_000 is 1%. The suffix `_micros` means millionths of a CURRENCY unit
everywhere else in this schema, and both records this one replaces are carried
in the migration ledger against G11 for hiding a percentage under it. This is
that entry's own `expected` spelling, taken on a new column where it costs
nothing, rather than as a rename of a column about to be dropped.

**NO DEFAULT ON THE COLUMN, AND THAT IS THE POINT.** UBB ships no catalogue: no
seeded markup, no starter percentage. A tenant that has declared nothing has NO
rung, and resolution answers `unknown` rather than a number. A column default of
zero would make "nobody has said what to charge" and "charge exactly what the
call cost" one answer — the silently wrong price #356 deleted from the resolver,
put back one layer down.

**NO UPLIFT COLUMN.** A rule that takes a margin over cost does not also carry a
flat addend (#147 §2), and that non-composition is what makes a resolved price
explicable by naming one thing. The per-event fixed uplift the two replaced
records carry is deleted rather than folded in, so the replacement is not built
with one.

**NO BACKFILL, AND NO DATA MIGRATION OBLIGATION.** Nothing is copied out of
`ubb_tenant_markup`: a migration cannot tell a tenant's ABSENT markup from a
deliberate zero, because both are `0` in that column, and inventing either
answer would seed exactly the value the rule above refuses. It is moot in
practice — UBB is deployed nowhere and holds no tenant data — and the migrations
squash at cutover. A tenant declares its rung through the route.
"""
import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0021_a_pricing_rule_declares_one_method'),
        ('tenants', '0024_remove_tenant_require_cost_card_coverage'),
    ]

    operations = [
        migrations.CreateModel(
            name='TenantDefaultMarkup',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('markup_micro_percent', models.BigIntegerField()),
                ('tenant', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='default_markup', to='tenants.tenant')),
            ],
            options={
                'db_table': 'ubb_tenant_default_markup',
            },
        ),
    ]
