"""A Measurement's value type is the registry's set, held by reference (#575).

STATE ONLY. `choices=` is not a database constraint, so this alters no column,
moves no row and runs no SQL that changes the table. The rule the database
enforces is `ck_measurement_value_type`, which already named the same two
values and is untouched.

What changed is where the model gets the list. It was the model's own pair,
each value beside an English word; it is now a comprehension over the set
generated from `measurement_value_type`, and both halves of each pair are the
identity — the wording belongs to the console's locale catalogue (ADR-0008 §4)
and nothing read the copy kept here. Django records `choices` in a field's
state, so the list a migration remembers has to follow.

The values are spelled out below rather than imported: a migration describes
the tree as it was on the day it was written, and one that read the generated
set would describe a different field after the registry next changed.

The reverse restores the earlier list, which is equally without effect on the
table.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event_types", "0007_the_last_published_declaration_is_kept"),
    ]

    operations = [
        migrations.AlterField(
            model_name="measurement",
            name="value_type",
            field=models.CharField(
                choices=[("decimal", "decimal"), ("integer", "integer")],
                default="integer", max_length=16),
        ),
    ]
