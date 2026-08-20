"""The rate's arithmetic shape takes its ratified name, and its values with it (#366).

The column that says how a rule computes — so much per unit of quantity, or a
component that applies once regardless — sat ONE CHARACTER from `pricing_mode`,
a declared concept meaning something entirely different: which pricing regime
governs a whole job. ADR-0006 §3 forbids two public terms whose difference is a
letter, and calls a pair like that a defect rather than a coincidence. #151
§13.2 ratified the replacement and #154 §3.3 locked it, so this is a forced
rename and not a preference.

**THE VALUES MOVE WITH THE NAME, AND ONE OF THEM IS INVISIBLE TO THE SWEEP.**
The value a flat per-event charge carried was `flat`, which
`domain-vocabulary/concepts/retired.yaml` records under `retired_senses` rather
than `retired_aliases` — `values_list(..., flat=True)` is Django's own keyword
and appears about a hundred times in first-party code, so sweeping the bare
token would condemn the ORM. That decision is right and it has a cost: the
forbidden-term sweep never had this value as input, so nothing mechanical could
find the rows carrying it or the branch reading them. They are converted here by
reading the model, and `fixed_component` is what they carry afterwards.

ADR-0007 §1 governs the shape: `RenameField`, never `AddField` plus
`RemoveField`. One `ALTER TABLE ... RENAME COLUMN` preserves every row; an
add-plus-remove would produce a column of the right name holding nothing, and
every test that only asks whether the new name exists would pass over the loss.
⚠ It is hand-written for the reason `0016` gives: `makemigrations` only asks
"did you rename this?" on a TTY, so a non-interactive run silently writes the
add-plus-remove ADR-0007 §1 forbids.

**No index or constraint is described over this column**, so unlike `0016` there
is no state-only half to re-describe: `Rate.Meta` names `measurement`, the ten
grouping slots and the two method columns, and none of them is this one. The
`AlterField` below records only that the column's `choices=` now come from the
registry's frozenset rather than from a hand-typed pair — the same members in
the same order, under their ratified spellings.

`old_name` is where a reader should look the retired word up. The migrations
tree is a declared sweep exclusion (`gates/forbidden-term-sweep.yaml`), so the
word legitimately survives in this file — which is the whole reason a rename
migration is allowed to name what it retires.

**The reverse carries its data too.** `fixed_component` goes back to `flat` and
the column goes back to its old name, so a rollback lands on rows the old code
can read rather than on a value its own branch would miss — the failure mode
that makes an un-reversed data migration worse than none.
"""

from django.db import migrations, models

from core.vocabulary import (
    RATE_STRUCTURE_FIXED_COMPONENT,
    RATE_STRUCTURE_PER_UNIT,
    RATE_STRUCTURE_VALUES,
)

#: What the fixed-component rows say today. Spelled once, here, because this is
#: a migration and naming the value it converts is the point — the same licence
#: `old_name` takes for the column.
THE_RETIRED_SENSE = "flat"


def _restate(apps, old, new):
    """Re-spell one arithmetic-shape value in place, and report what moved.

    ⚠ Written through the HISTORICAL model rather than the live one, which is
    what makes this replayable: `apps.get_model` builds the class from the
    migration state at this point in the history, so a later ticket moving the
    rate to another table cannot silently change what this conversion touched.

    The count is printed where `migrate --verbosity 2` shows it rather than
    swallowed. It may legitimately be zero — a tree whose rates are all per-unit
    has nothing to convert — and that is a different fact from a query matching
    nothing because it was asked the wrong question.
    """
    Rate = apps.get_model("pricing", "Rate")
    moved = Rate.objects.filter(rate_structure=old).update(rate_structure=new)
    if moved:
        print(f"  {moved} rate(s): {old} -> {new}")


def to_the_ratified_value(apps, schema_editor):
    _restate(apps, THE_RETIRED_SENSE, RATE_STRUCTURE_FIXED_COMPONENT)


def back_to_the_retired_sense(apps, schema_editor):
    _restate(apps, RATE_STRUCTURE_FIXED_COMPONENT, THE_RETIRED_SENSE)


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0025_a_resolution_run_is_recorded_once_and_never_edited'),
    ]

    operations = [
        migrations.RenameField(
            model_name='rate',
            old_name='pricing_model',
            new_name='rate_structure',
        ),
        # AFTER the rename, so the update addresses the column by the name the
        # model now uses — `apps.get_model` builds its class from the migration
        # state, and at this point that state has the new name.
        migrations.RunPython(to_the_ratified_value,
                             back_to_the_retired_sense),
        migrations.AlterField(
            model_name='rate',
            name='rate_structure',
            field=models.CharField(
                choices=[(value, value) for value in sorted(RATE_STRUCTURE_VALUES)],
                default=RATE_STRUCTURE_PER_UNIT, max_length=20),
        ),
    ]
