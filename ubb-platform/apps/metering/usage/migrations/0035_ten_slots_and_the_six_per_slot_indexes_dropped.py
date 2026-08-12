"""Ten slots on the posting, under the canonical noun, with no index of their own (#276).

Three things happen here and they are deliberately ONE migration.

**The six slots become ten.** #273 closed the free-form grouping escape hatch —
the surviving open bag is filterable and readable but never groupable — so
demand that used to land there now has to arrive as a declaration or not arrive
at all. Ten is v1 product headroom for that demand. The four always-present axes
(`provider`, `event_type`, `task_type`, `subtask_type`) are untouched.

**The slots stop costing anything on insert.** Six of them carried an index each
and a composite led with two more, so seven of the index writes this table paid
on every insert — the hottest insert path in the system — were attributable to
the slots alone. Widening to ten under that arrangement would have taxed every
insert for capacity nobody is using yet, which is the whole reason the widening
and the cleanup are not two changes. The table's other indexes are untouched.

The per-column indexes go because a cardinality-capped column is around one
percent selective, and at that selectivity the planner reaches for a sequential
scan or a composite anyway.

`idx_usage_dim_attribution` goes for a sharper reason: **nothing in this
repository filters on a slot.** Every read of one is a `GROUP BY` of a single
slot inside a tenant (sometimes a customer) and an `effective_at` window —
`apps.metering.queries.get_dimensional_margin`, `get_usage_timeseries`,
`get_customer_billed_breakdown`, and the `/analytics/usage` breakdowns. The
columns that select the rows are `tenant`/`customer` and `effective_at`, and
those are exactly what `idx_usage_tenant_effective` and
`idx_usage_customer_effective` lead with; those two are the composites that
match a real query shape, and they still match it at ten columns. A composite
led by two slots could only ever be scanned whole. "The first two of ten" is
also arbitrary in a way that "the first two of six" merely looked like it
wasn't — six slots were all a tenant had, so leading with two of them at least
read as a guess about the popular ones.

**The columns take the canonical noun.** Not forced by the forbidden-term sweep
— the abbreviation these columns carried is not a whole-token match for the
retired word, and the sweep has never counted them — but by ADR-0006 §2, which
refuses a short form beside a long form, and by the fact that these columns are
being rebuilt regardless. `old_name` below is where a reader should look the
abbreviation up. The six PUBLISHED properties that share that abbreviation are
**not** renamed here; see the note on `_RENAMES`.

ADR-0007 §1 governs the shape: `RenameField` for all six, never `AddField` plus
`RemoveField`. The four genuinely new columns are `AddField` because there is
nothing to carry — a column that never existed has no data to lose.

**Order matters and is not incidental.** The composite is dropped first, while
the state still describes it in terms the columns answer to; then the six
per-column indexes are dropped by `AlterField`, while the auto-generated index
names still spell the columns they cover; then the renames run; then the four
new columns arrive already unindexed. Renaming first would leave every one of
those drops referring to a column under a name Postgres had just changed —
Django resolves them by column rather than by name, so it would still work, and
the DDL would be that much harder to read in a log.

Nothing here needs the `SeparateDatabaseAndState` correction #275 needed: after
the composite is dropped, no `Meta.indexes` or `Meta.constraints` entry on this
model names a slot, so there is no state description left to drift.

The reverse re-creates the composite over the two slots it used to lead with,
puts the six per-column indexes back and renames the columns home. It drops the
four new columns, which is the one thing it cannot do losslessly — values
attributed to a slot that did not exist before this migration have nowhere to
go, and Django's own `AddField` reverse is what discards them.
"""

from django.db import migrations, models

#: The six renames, as (retired, canonical) pairs.
#:
#: The retired spelling survives in exactly one other place after this change,
#: and on purpose: it is still the name of six PUBLISHED properties on the rate
#: schemas and three on the posting detail response (`api/v1/schemas.py`).
#: Nothing about the contract moves here. Ticket 20 replaces the posting's with
#: one object keyed by the tenant's own declared key; the rate's wait for slice
#: 4, which rebuilds that entity. Until then the column and the property are two
#: names for one value, joined by the serializers rather than by spelling.
#:
#: The test module named for this migration reads both halves off the operations
#: below rather than spelling either, which is what stops its assertions drifting
#: from what actually ran.
_RENAMES = [(f"dim{i}", f"grouping_field_{i}") for i in range(1, 7)]

#: The four that are new. Ten is the registry's count
#: (`apps.platform.grouping_fields.models.SLOT_CHOICES`); the test module holds
#: the two to each other so a widening on one side cannot ship alone.
_ADDITIONS = [f"grouping_field_{i}" for i in range(7, 11)]


def _slot_column(**kwargs):
    return models.CharField(max_length=100, blank=True, default="", **kwargs)


class Migration(migrations.Migration):

    dependencies = [
        ('usage', '0034_the_measured_quantities_take_the_canonical_name'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='posting',
            name='idx_usage_dim_attribution',
        ),
        # The six per-slot indexes, dropped off the columns while they still
        # answer to the names their auto-generated indexes were built under.
        *[migrations.AlterField(model_name='posting', name=retired,
                                field=_slot_column())
          for retired, _ in _RENAMES],
        *[migrations.RenameField(model_name='posting', old_name=retired,
                                 new_name=canonical)
          for retired, canonical in _RENAMES],
        *[migrations.AddField(model_name='posting', name=canonical,
                              field=_slot_column())
          for canonical in _ADDITIONS],
    ]
