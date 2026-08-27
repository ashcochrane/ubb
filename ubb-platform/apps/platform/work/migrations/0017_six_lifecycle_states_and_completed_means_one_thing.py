"""Six lifecycle states, and `completed` comes to mean one thing (#408).

The declared set gains `cancelled` and `expired`, and the four it already held
stop overlapping. `active` is the only non-terminal state; the other five are
told apart by WHO WROTE THEM, which is the property every money decision later
in this slice rests on:

  `completed` the tenant declared delivery, and nothing else writes it.
  `failed`    the tenant declared the work could not be delivered.
  `cancelled` deliberately stopped or withdrawn, including by a close cascade.
  `killed`    UBB stopped it on a spend signal, and nothing tenant-declared
              lands here.
  `expired`   nobody ever told UBB how it ended. Either sweeper.

**COLUMN-ONLY, AND DELIBERATELY SO: NO ROW IS REWRITTEN.** The four existing
values keep their spelling and every existing row keeps its value, so this is
an `AlterField` and nothing else. A back-fill would have to decide, per row,
whether a historical `completed` meant a declared delivery or a sweeper giving
up — and the reason that question cannot be answered is the whole defect this
ticket exists to remove. Guessing an answer now would write the ambiguity into
the record permanently instead of ending it, so the honest boundary is the
commit: rows written before it carry the old meaning, rows after it carry the
new one, and no row is made to claim a provenance nobody recorded.

**THE REVERSE IS EXACT AND UNCONDITIONALLY SAFE**, which is the one thing worth
checking about a choices change that can shrink a value set: no row holds
`cancelled` or `expired` at the moment this runs, because nothing has written
either yet. `choices` is a validation-layer declaration rather than a database
constraint in any case, so neither direction touches the stored data.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0016_one_column_carries_the_declared_kind_of_work'),
    ]

    operations = [
        migrations.AlterField(
            model_name='task',
            name='status',
            field=models.CharField(choices=[('active', 'Active'), ('completed', 'Completed'), ('failed', 'Failed'), ('cancelled', 'Cancelled'), ('killed', 'Killed'), ('expired', 'Expired')], db_index=True, default='active', max_length=20),
        ),
    ]
