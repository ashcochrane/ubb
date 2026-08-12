"""The registry's stored slot identifier takes the canonical noun (#276).

THE ONE DATA-CARRYING HALF OF THE WIDENING. Everything else in #276 is DDL:
columns renamed, columns added, indexes dropped. This migration rewrites rows.

`GroupingField.slot` does not merely resemble a column name — **it is one**.
`DimensionService.admit` returns `{slot: value}` and the recording path hands
that map straight to the posting's `create()` as keyword arguments, so a
registry row saying `slot="<something>"` is a claim that a column of exactly
that name exists. Rename the columns without rewriting these rows and every
declared field stops resolving; rewrite these rows without renaming the columns
and the same thing happens from the other side. The two are one change split
across four migrations only because they live in four apps, and the dependency
list below is what makes that split a total order in both directions.

**Why an explicit `RunPython` and not something cleverer.** There is no
mechanical rewrite available: the mapping is between two vocabularies, not two
spellings of one. The reverse is written out rather than inferred for the same
reason, and it is exercised by a test — `test_ten_slots_take_the_canonical_noun`
drives both directions against real rows. A slot identifier rewritten with no
reverse is a one-way door on a live registry, and the door is worth more than the
twenty lines.

**Both directions refuse rather than guess.** A row carrying a slot neither
vocabulary contains is data this migration does not understand, and leaving it
alone would leave the registry pointing at no column at all — a declared field
that silently groups nothing. Refusing is louder and cheaper to fix.

**The reverse cannot carry a slot above six, and says so.** Slots seven to ten
have no counterpart in the vocabulary this migration replaces, because the
columns behind them did not exist. A tenant that has declared one of them has a
registry the older schema cannot express, so the reverse stops rather than
silently unbinding a live declaration. Reversing is still available the moment
those declarations are removed, which is the honest shape of the constraint:
this is not irreversible, it is reversible on a condition the operator can meet.

**The widening of the column comes first, and has to.** The canonical
identifiers are longer than the ones they replace; writing them into a column
still bounded at the old width would truncate every one of them. `AlterField`
carries the new bound and the ten-member choice list together, because both
describe the same widening.
"""

from django.db import migrations, models

#: The rewrite, in the only direction it can be stated once: `slot` N of the
#: retired vocabulary becomes slot N of the canonical one. Six pairs, because
#: six is what the retired vocabulary had.
_REWRITE = {f"dim{i}": f"grouping_field_{i}" for i in range(1, 7)}
_UNWIND = {canonical: retired for retired, canonical in _REWRITE.items()}


def _apply(apps, mapping, *, direction):
    """Rewrite every stored slot through `mapping`, refusing anything else."""
    GroupingField = apps.get_model("grouping_fields", "GroupingField")
    unknown = sorted(set(
        GroupingField.objects.exclude(slot__in=mapping)
        .values_list("slot", flat=True).distinct()))
    if unknown:
        raise RuntimeError(
            f"cannot rewrite the registry {direction}: "
            f"{len(unknown)} declared slot(s) have no counterpart in the target "
            f"vocabulary ({', '.join(repr(s) for s in unknown)}). Rewriting the "
            "rest would leave those declarations bound to a column that does not "
            "exist. Remove or re-declare them first.")
    for source, target in mapping.items():
        GroupingField.objects.filter(slot=source).update(slot=target)


def forwards(apps, schema_editor):
    _apply(apps, _REWRITE, direction="onto the canonical noun")


def backwards(apps, schema_editor):
    _apply(apps, _UNWIND, direction="back onto the retired abbreviation")


class Migration(migrations.Migration):

    dependencies = [
        ('grouping_fields', '0003_the_grouping_field_takes_its_name'),
        # The columns the identifiers below name. Declared so that a forward
        # run creates the columns before the registry points at them, and a
        # reverse run un-points the registry before the columns go away.
        ('usage', '0035_ten_slots_and_the_six_per_slot_indexes_dropped'),
        ('pricing', '0017_ten_slots_on_the_rate'),
        ('work', '0013_ten_slots_on_the_task'),
    ]

    operations = [
        migrations.AlterField(
            model_name='groupingfield',
            name='slot',
            field=models.CharField(
                choices=[(f"grouping_field_{i}", f"grouping_field_{i}")
                         for i in range(1, 11)],
                max_length=17),
        ),
        migrations.RunPython(forwards, backwards, elidable=False),
    ]
