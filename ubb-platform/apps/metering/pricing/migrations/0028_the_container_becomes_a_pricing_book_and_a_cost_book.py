"""The container splits into a Pricing Book and a cost book, and the record
that assigns a book to a customer is deleted outright (#368, spec §1, §6).

**THE SPLIT.** One table served as both a book of supplier costs and a book of
customer prices, told apart by a `cost`/`price` word. That is the conflation
the whole slice exists to end (#148 §5.4), and a discriminator cannot express
the thing that is actually true of the two: they have DIFFERENT COLUMNS. A cost
is observed, from a named supplier, in whatever currency that supplier bills —
so a cost book is pinned to a provider and to a currency. A price is decided by
the tenant and does not move because the tenant switched supplier — so a
Pricing Book is pinned to neither. After this migration the two are separate
tables whose columns disagree, which is the statement the column could never
make.

**THE NAME.** The container is a `PricingBook` on `ubb_pricing_book`. #367 took
the misnamed rate off `ubb_rate_card` and deliberately left the freed name
alone, because this ticket does not rename the container so much as split it —
renaming it there and again here would have been two renames of one table to
reach one name. `AlterModelTable` IS the rename operation for a `db_table`
change; `RenameModel` moves the Python class and, with `db_table` explicit, does
nothing at the database. Both are in `usage/tests/test_posting_rename.py`'s list
of operations that carry rows rather than rebuild them.

**THE THIRD TABLE IS DELETED, NOT RENAMED.** `RateCardAssignment` recorded which
book a customer was assigned to. Its job passed to the Plan's required book
reference in #362, which is where a customer's pricing already resolves from, so
there is nothing left for it to answer. That deletion is what discharges #193
§L's "one deleted currency column" for this slice.

⚠ **THERE IS NO DATA MIGRATION AND NO BACKFILL, AND THAT IS A DECISION RATHER
THAN AN OMISSION.** Rows that today carry the kind word `cost` become Pricing
Book rows, because the rename carries the whole table and this migration writes
no conversion to move them. That would be wrong on a deployed system and is
correct here: **UBB is deployed nowhere and holds no tenant data**, and #155 §11
squashes every migration at cutover, so the fresh initial set creates
`ubb_pricing_book` and `ubb_cost_book` in their final shapes with nothing to
carry. Writing a splitter would be writing, testing and reviewing a conversion
for zero rows, and then deleting it. **UBB also ships no catalogue** — no
starter Pricing Book, no default rule set, no seeded markup — so nothing here
creates a row either.

⚠ **HAND-WRITTEN, for the reason `0016`, `0026` and `0027` all give.**
`makemigrations` only asks "did you rename this?" on a TTY, so a non-interactive
run writes the add-plus-remove pair ADR-0007 §1 forbids, silently, and every
test that asks only whether the new name exists passes over the loss. Nothing
here was generated.

**WHY THE RULE AND THE PUBLISH RECORD EACH GAIN A SECOND COLUMN.** Both point at
a book, and there are two kinds of book now, so each carries one nullable
reference per kind with a `CHECK` refusing both at once. The alternative — two
rule tables and two publish tables — would put the discriminator back as a table
name and duplicate every act that is genuinely one act: changing a book is one
thing whichever kind of book it is.

⚠ **AND THE UNIQUENESS KEY BECOMES TWO KEYS, WHICH IS THE PART THAT WOULD HAVE
FAILED SILENTLY.** One key naming both book columns would carry a NULL in one of
them on every single row, and Postgres treats NULLs in a unique index as
DISTINCT — so no two rows would ever collide and `uq_rate_active_in_book` would
have survived as a no-op wearing its own name. Two partial keys, each scoped to
the half whose column is present, is what keeps the rule a rule.

**THE REVERSE IS DJANGO'S OWN INVERSE, AND NOTHING HERE RUNS IT.** There is no
`RunPython` in this file, so the convention asking for a hand-written reverse
that a test actually exercises (`docs/conventions/django-patterns.md`) does not
bind: every operation is one Django reverses itself — the renames swap back,
the removed columns come back at their previous definitions, and the created
table drops. ⚠ What no inverse restores is DATA: the container's
`card_type`, `provider_key` and `currency` VALUES go with their columns, and the
assignment table's rows go with the table. Both are stated rather than papered
over — this tree is deployed nowhere and every one of those tables is empty.
The heading used to read "THE REVERSE IS RUN, NOT ASSERTED", which was the one
thing in it that was not true.

The migrations tree is a declared sweep exclusion
(`gates/forbidden-term-sweep.yaml`), so the retired words legitimately survive
in this file, which is the whole reason a rename migration is allowed to name
what it retires.
"""

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0027_the_rate_moves_to_the_table_named_for_a_rate'),
        ('customers', '0001_initial'),
        ('tenants', '0001_initial'),
    ]

    operations = [
        # --- The rule's pointer, renamed before the model it points at -------
        #
        # The key names the column, so it comes off first: Django's state may
        # not hold a constraint over a field that is about to move. It is
        # rebuilt at the bottom as TWO partial keys — see the module docstring
        # for why one key over both columns would enforce nothing.
        migrations.RemoveConstraint(
            model_name='rate',
            name='uq_rate_active_in_book',
        ),
        migrations.RenameField(
            model_name='rate',
            old_name='rate_card',
            new_name='pricing_book',
        ),
        # --- The publish record's pointer, the same move -------------------
        migrations.RemoveIndex(
            model_name='pricingbookpublish',
            name='idx_book_publish_pending',
        ),
        migrations.RenameField(
            model_name='pricingbookpublish',
            old_name='book',
            new_name='pricing_book',
        ),
        # --- The container becomes the Pricing Book -------------------------
        #
        # All three keys name a column that is leaving or a shape that is
        # changing, so all three come off before the rename and the survivors
        # are re-declared afterwards under names that say what they now mean.
        migrations.RemoveConstraint(
            model_name='ratecard',
            name='uq_ratecard_tenant_key',
        ),
        migrations.RemoveConstraint(
            model_name='ratecard',
            name='uq_ratecard_one_default_per_provider',
        ),
        migrations.RemoveConstraint(
            model_name='ratecard',
            name='uq_pricing_book_one_override_per_customer',
        ),
        # THE MODEL, THEN THE TABLE. `RenameModel` moves the Python class and
        # repoints every reference to it in state — including `plans.Plan`'s
        # required book reference in another app, which is why that app needs
        # no migration of its own. With `db_table` explicit it issues no DDL;
        # `AlterModelTable` below is the statement that renames the table, and
        # one `ALTER TABLE ... RENAME TO` preserves every row, index,
        # constraint and trigger, because those belong to the table by
        # identity rather than by name.
        migrations.RenameModel(
            old_name='RateCard',
            new_name='PricingBook',
        ),
        migrations.AlterModelTable(
            name='pricingbook',
            table='ubb_pricing_book',
        ),
        # THE KIND WORD, AND THE TWO COLUMNS A PRICE DOES NOT HAVE. Three
        # removals with nothing added to pair them with, which is what makes
        # them deletions rather than renames. The currency is the one that
        # discharges a debt: `usage/tests/test_posting_rename.py` records seven
        # currency columns nobody owns, and this table's line leaves that list
        # because the column leaves the table — the gap is paid rather than
        # moved to a new spelling.
        migrations.RemoveField(
            model_name='pricingbook',
            name='card_type',
        ),
        migrations.RemoveField(
            model_name='pricingbook',
            name='provider_key',
        ),
        migrations.RemoveField(
            model_name='pricingbook',
            name='currency',
        ),
        migrations.AddConstraint(
            model_name='pricingbook',
            constraint=models.UniqueConstraint(
                fields=('tenant', 'key'), name='uq_pricing_book_tenant_key'),
        ),
        migrations.AddConstraint(
            model_name='pricingbook',
            constraint=models.UniqueConstraint(
                condition=models.Q(('is_default', True)), fields=('tenant',),
                name='uq_pricing_book_one_default'),
        ),
        migrations.AddConstraint(
            model_name='pricingbook',
            constraint=models.UniqueConstraint(
                condition=models.Q(('customer__isnull', False)),
                fields=('customer',),
                name='uq_pricing_book_one_override_per_customer'),
        ),
        # --- The cost book, a new table in its final shape ------------------
        #
        # A brand-new model is the one thing `makemigrations` cannot get wrong
        # (there is no rename to miss), and it is written out here anyway
        # because the rest of the file is hand-written and a half-generated
        # migration is worse than either.
        migrations.CreateModel(
            name='CostBook',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('provider_key', models.CharField(blank=True, default='',
                                                  max_length=100)),
                ('currency', models.CharField(max_length=3)),
                ('key', models.SlugField(max_length=64)),
                ('name', models.CharField(blank=True, default='',
                                          max_length=255)),
                ('version', models.PositiveIntegerField(default=1)),
                ('is_default', models.BooleanField(default=False)),
                ('tenant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='cost_books', to='tenants.tenant')),
            ],
            options={
                'db_table': 'ubb_cost_book',
            },
        ),
        migrations.AddConstraint(
            model_name='costbook',
            constraint=models.UniqueConstraint(
                fields=('tenant', 'key'), name='uq_cost_book_tenant_key'),
        ),
        migrations.AddConstraint(
            model_name='costbook',
            constraint=models.UniqueConstraint(
                condition=models.Q(('is_default', True)),
                fields=('tenant', 'provider_key', 'currency'),
                name='uq_cost_book_one_default_per_provider'),
        ),
        # THE CURRENCY IS DECLARED, AND THIS IS WHAT SAYS SO. A cost book that
        # does not name the currency its supplier bills in prices nothing that
        # can be trusted — so the empty string is refused at the database
        # rather than defaulted to the tenant's own frozen choice, which is
        # what made the column it replaces an unowned copy.
        migrations.AddConstraint(
            model_name='costbook',
            constraint=models.CheckConstraint(
                condition=~models.Q(('currency', '')),
                name='ck_cost_book_names_its_currency'),
        ),
        # --- The second pointer on each record that names a book ------------
        migrations.AddField(
            model_name='rate',
            name='cost_book',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='rates', to='pricing.costbook'),
        ),
        migrations.AddField(
            model_name='pricingbookpublish',
            name='cost_book',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='publishes', to='pricing.costbook'),
        ),
        migrations.AlterField(
            model_name='pricingbookpublish',
            name='pricing_book',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='publishes', to='pricing.pricingbook'),
        ),
        migrations.AddIndex(
            model_name='pricingbookpublish',
            index=models.Index(fields=['pricing_book', 'declaration_status'],
                               name='idx_book_publish_pending'),
        ),
        migrations.AddIndex(
            model_name='pricingbookpublish',
            index=models.Index(fields=['cost_book', 'declaration_status'],
                               name='idx_cost_book_publish_pending'),
        ),
        migrations.AddConstraint(
            model_name='pricingbookpublish',
            constraint=models.CheckConstraint(
                condition=models.Q(('cost_book__isnull', False),
                                   ('pricing_book__isnull', False),
                                   _negated=True),
                name='ck_book_publish_at_most_one_book'),
        ),
        # --- The rule's two keys and its at-most-one-book rule ---------------
        migrations.AddConstraint(
            model_name='rate',
            constraint=models.UniqueConstraint(
                condition=models.Q(('pricing_book__isnull', False),
                                   ('valid_to__isnull', True)),
                fields=('pricing_book', 'measurement', 'currency', 'provider',
                        'event_type', 'task_type', 'subtask_type',
                        'grouping_field_1', 'grouping_field_2',
                        'grouping_field_3', 'grouping_field_4',
                        'grouping_field_5', 'grouping_field_6',
                        'grouping_field_7', 'grouping_field_8',
                        'grouping_field_9', 'grouping_field_10'),
                name='uq_rate_active_in_pricing_book'),
        ),
        migrations.AddConstraint(
            model_name='rate',
            constraint=models.UniqueConstraint(
                condition=models.Q(('cost_book__isnull', False),
                                   ('valid_to__isnull', True)),
                fields=('cost_book', 'measurement', 'currency', 'provider',
                        'event_type', 'task_type', 'subtask_type',
                        'grouping_field_1', 'grouping_field_2',
                        'grouping_field_3', 'grouping_field_4',
                        'grouping_field_5', 'grouping_field_6',
                        'grouping_field_7', 'grouping_field_8',
                        'grouping_field_9', 'grouping_field_10'),
                name='uq_rate_active_in_cost_book'),
        ),
        migrations.AddConstraint(
            model_name='rate',
            constraint=models.CheckConstraint(
                condition=models.Q(('cost_book__isnull', False),
                                   ('pricing_book__isnull', False),
                                   _negated=True),
                name='ck_rate_sits_in_at_most_one_book'),
        ),
        # The rule's own back-references stop being named for the container.
        # State only — a `related_name` is not a column.
        migrations.AlterField(
            model_name='rate',
            name='tenant',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='rules', to='tenants.tenant'),
        ),
        migrations.AlterField(
            model_name='rate',
            name='customer',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='rules', to='customers.customer'),
        ),
        migrations.AlterField(
            model_name='pricingbook',
            name='tenant',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='pricing_books', to='tenants.tenant'),
        ),
        # --- The assignment record, deleted outright ------------------------
        migrations.DeleteModel(
            name='RateCardAssignment',
        ),
    ]
