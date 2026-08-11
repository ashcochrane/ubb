"""The measured-quantity bag takes the canonical measurement name (#274).

A RENAME, AND ONLY A RENAME. The column keeps its type, its default, its
contents and its meaning; what changes is that it is now named for the thing its
keys are keys **into**. #263 built the declarations beneath an Event Type — a
code, a value type, a unit, a source — and this bag's keys are those codes. The
old name described a container the caller filled; the new one names the lookup
that makes a quantity *costable* rather than merely carried.

ADR-0007 §1 governs, and the pre-squash exemption is spent: `RenameField`, never
`AddField` plus `RemoveField`. The difference is not stylistic. A rename is one
`ALTER TABLE ... RENAME COLUMN`, which preserves every row, the index behind the
primary key, and the child's one-to-one constraint. An add-plus-remove produces a
column of the right name holding nothing, and every test that only asks whether
the new name exists would pass over the loss. `tests/
test_the_measured_quantities_take_the_canonical_name.py` reads its two names off
the operation below rather than spelling them, so the assertions cannot drift
from what actually ran — and this file stays the only place in the tree that
still writes the retired word, which is where a reader should be looking it up.

**No behaviour moves with the name.** The only validation the bag has ever
carried is that its values are not negative, and that validator moved across
unchanged, on the request schema where it already lived. Tightening it — refusing
a quantity no declaration matches — is slice 3's, which owns every behaviour a
declaration selects. Today such a quantity still meets a `continue` on the price
side and still contributes nothing; naming the field is what makes that
describable, not what fixes it.

The reverse is the same operation in the other direction and loses nothing.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('usage', '0033_the_second_open_bag_folds'),
    ]

    operations = [
        migrations.RenameField(
            model_name='postingmeasurement',
            old_name='usage_metrics',
            new_name='measurements',
        ),
    ]
