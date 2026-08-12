"""The rate's quantity name takes the canonical measurement name (#275).

A RENAME, AND ONLY A RENAME — and here that phrase carries a second meaning it
did not carry for #274. This column names the quantity a rate prices, and the
name is **still free text after this migration runs**. Slice 3 replaces it with
a reference to the declared record the name is a name *of*; slice 2 pays the
word and nothing else. ADR-0007 §3 is what sanctions that split — final name,
final contract, implementation partly built — and the alternative was worse in
both directions: renaming later would break the contract twice, and building the
reference here would pull slice 3's whole rating path forward.

**Why a column on an entity slice 4 rebuilds is renamed at all.** The debt
reaches the rate model, the book service, the pricing service, the rate cache
and roughly a dozen pricing tests, while the rate itself survives to slice 4 —
which looks exactly like the "renaming a table a later slice deletes" work the
migration decision warns against. It was weighed: the ledger owns this at slice
2, an owner may move earlier but never later, and there is no re-owning
mechanism. So it lands here.

ADR-0007 §1 governs the shape: `RenameField`, never `AddField` plus
`RemoveField`. One `ALTER TABLE ... RENAME COLUMN` preserves every row and every
index and constraint built over the column, and Postgres carries both
`idx_ratecard_lookup` and `uq_rate_active_in_book` across the rename itself —
which is why the two state operations below are wrapped in
`SeparateDatabaseAndState` with no database half. Their *definitions* have not
changed; only the name Django's migration state uses to describe them has, and
dropping and rebuilding a live unique index to record a spelling would be real
downtime bought for nothing.

An add-plus-remove would instead produce a column of the right name holding
nothing, and every test that only asks whether the new name exists would pass
over the loss. The module beside this one in `pricing/tests/`, named for this
migration, reads both names off the operation below rather than spelling them,
so its assertions cannot drift from what actually ran, and `old_name` here is where
a reader should look the retired word up — the migrations tree being one of the
two declared sweep exclusions where it legitimately survives, the contract
gate's reviewed-break block being the other.

**No behaviour moves with the name.** Rate resolution still matches on the
column's exact text, a rate naming a quantity no event carries still matches
nothing, and a quantity no rate names still meets a `continue` on the price side
and contributes nothing. Making the first of those describable is what this
migration does; making the last of them refusable is slice 3's, which owns every
behaviour a declaration selects.

The reverse is the same operation in the other direction and loses nothing.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0015_remove_rate_uq_rate_active_in_book_rate_dim1_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='rate',
            old_name='metric_name',
            new_name='measurement_key',
        ),
        # STATE ONLY, both directions. See the module docstring: the index and
        # the constraint are unchanged as database objects, so the database
        # half of this is empty by design rather than by omission.
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveIndex(
                    model_name='rate',
                    name='idx_ratecard_lookup',
                ),
                migrations.AddIndex(
                    model_name='rate',
                    index=models.Index(
                        fields=['tenant', 'card_type', 'provider', 'event_type',
                                'measurement_key'],
                        name='idx_ratecard_lookup'),
                ),
                migrations.RemoveConstraint(
                    model_name='rate',
                    name='uq_rate_active_in_book',
                ),
                migrations.AddConstraint(
                    model_name='rate',
                    constraint=models.UniqueConstraint(
                        condition=models.Q(('valid_to__isnull', True)),
                        fields=('rate_card', 'measurement_key', 'currency',
                                'provider', 'event_type', 'task_type',
                                'subtask_type', 'dim1', 'dim2', 'dim3', 'dim4',
                                'dim5', 'dim6'),
                        name='uq_rate_active_in_book'),
                ),
            ],
        ),
    ]
