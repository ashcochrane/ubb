"""A Grouping Field's scope is the registry's set, held by reference (#575).

STATE ONLY. `choices=` is not a database constraint, so this alters no column,
moves no row and runs no SQL that changes the table.

What changed is where the model gets the list. It was three pairs typed beside
the model, each value with an English word; it is now a comprehension over the
set generated from `grouping_field_scope`, and both halves of each pair are the
identity — the wording belongs to the console's locale catalogue (ADR-0008 §4)
and nothing read the copy kept here. Django records `choices` in a field's
state, so the list a migration remembers has to follow.

The values are spelled out below rather than imported: a migration describes
the tree as it was on the day it was written, and one that read the generated
set would describe a different field after the registry next changed.

Nothing here refuses a stored scope outside the three. The same ticket made the
declaration route refuse one, which is the door a scope arrives through; a row
written before that keeps whatever it was sent.

The reverse restores the earlier list, which is equally without effect on the
table.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("grouping_fields",
         "0004_the_stored_slot_identifier_takes_the_canonical_noun"),
    ]

    operations = [
        migrations.AlterField(
            model_name="groupingfield",
            name="scope",
            field=models.CharField(
                choices=[("event", "event"), ("subtask", "subtask"),
                         ("task", "task")],
                default="event", max_length=8),
        ),
    ]
