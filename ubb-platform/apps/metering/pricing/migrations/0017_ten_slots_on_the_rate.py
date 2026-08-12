"""The rate's selector slots become ten, under the canonical noun (#276).

The registry widened to ten and the posting grew ten columns to hold the
values. This is the third side of the same triangle: a slot a tenant can
declare and attribute but cannot PRICE on would be a grouping axis that
silently is not a rate selector, which is exactly the split design D3 exists to
close. `apps.platform.tests.test_grouping_field_invariants` pins the two lists
to each other, so they cannot widen one at a time.

ADR-0007 §1 governs the shape: `RenameField` for the six that already hold
values, `AddField` for the four that never existed and so have nothing to
carry.

**The unique constraint is dropped and rebuilt, and that is not an
add-plus-remove.** ADR-0007 §1 is about columns and their data; this is one
database object whose column list genuinely changes — four columns join it —
and Django has no operation that alters a constraint in place. The rebuild also
disposes of the state-description problem #275 had to solve with an empty
`SeparateDatabaseAndState`: there is no point correcting the state's description
of a constraint that is about to be replaced wholesale, so the remove runs
FIRST, before the renames leave it describing columns the state no longer has.

`idx_ratecard_lookup` names none of these columns and is untouched.

**What this migration does not do.** Six of these ten reach the published
contract as `RateIn`/`RateChangeIn`/`RateOut` properties, and those properties
keep their names and their count. A caller can still pin only six of the ten,
which is a real gap and a deliberate one: this ticket's acceptance criteria
forbid renaming a published property, and NO LATER SLICE-2 TICKET WIDENS THESE
— ticket 20 replaces the posting's slot properties and ticket 21 renames the
Grouping Field route family; neither touches the rate. This entity's published
surface is rebuilt in slice 4. Until then the extra four are reachable only by a
rate written server-side.

The reverse renames the six home and drops the four, restoring the constraint
over the original thirteen columns. A rate pinned on a slot above six cannot
survive that, which is `AddField`'s reverse discarding the column, and is the
honest answer: those rates price on an axis the older schema cannot express.
"""

from django.db import migrations, models

#: The six renames, as (retired, canonical) pairs — the same abbreviation the
#: posting's own slots carried, and the same reason for retiring it (ADR-0006
#: §2). The published property names are NOT these; see the docstring.
_RENAMES = [(f"dim{i}", f"grouping_field_{i}") for i in range(1, 7)]

_ADDITIONS = [f"grouping_field_{i}" for i in range(7, 11)]

#: The active-row uniqueness, in both shapes. Spelled out rather than derived
#: from the model: a migration that read today's model would stop describing
#: what it did the moment the model moved again.
_ACTIVE_ROW_UNIQUE = "uq_rate_active_in_book"
_HEAD = ("rate_card", "measurement_key", "currency", "provider", "event_type",
         "task_type", "subtask_type")


def _slot_column():
    return models.CharField(max_length=100, blank=True, default="")


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0016_the_rates_quantity_name_takes_the_canonical_name'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='rate',
            name=_ACTIVE_ROW_UNIQUE,
        ),
        *[migrations.RenameField(model_name='rate', old_name=retired,
                                 new_name=canonical)
          for retired, canonical in _RENAMES],
        *[migrations.AddField(model_name='rate', name=canonical,
                              field=_slot_column())
          for canonical in _ADDITIONS],
        migrations.AddConstraint(
            model_name='rate',
            constraint=models.UniqueConstraint(
                condition=models.Q(('valid_to__isnull', True)),
                fields=_HEAD + tuple(canonical for _, canonical in _RENAMES)
                + tuple(_ADDITIONS),
                name=_ACTIVE_ROW_UNIQUE),
        ),
    ]
