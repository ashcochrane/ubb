"""The task's declared values become ten, under the canonical noun (#276).

Task-scoped values (design D6) are set once on the unit of work and inherited by
every event in its tree. There are ten of them for the same reason there are ten
on the posting and ten on the rate: a slot whose value can be sent per event but
not attached to the job would work differently depending on where the value came
from, which is the inheritance rule leaking into the vocabulary.

ADR-0007 §1: `RenameField` for the six that hold values, `AddField` for the four
that never existed.

No index or constraint on this model names a slot — task-scoped values are read
through the unit they hang off, never queried on directly — so there is no state
description to correct and no `SeparateDatabaseAndState` here.

The reverse renames the six home and drops the four.
"""

from django.db import migrations, models

_RENAMES = [(f"dim{i}", f"grouping_field_{i}") for i in range(1, 7)]

_ADDITIONS = [f"grouping_field_{i}" for i in range(7, 11)]


def _slot_column():
    return models.CharField(max_length=100, blank=True, default="")


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0012_rename_app_label_content_types'),
    ]

    operations = [
        *[migrations.RenameField(model_name='task', old_name=retired,
                                 new_name=canonical)
          for retired, canonical in _RENAMES],
        *[migrations.AddField(model_name='task', name=canonical,
                              field=_slot_column())
          for canonical in _ADDITIONS],
    ]
