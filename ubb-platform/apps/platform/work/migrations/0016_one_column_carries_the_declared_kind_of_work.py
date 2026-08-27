"""One column carries the declared kind of work, at either altitude (#407).

`Task.task_type` and `Task.subtask_type` were set exclusively — one for a whole
unit of work, one for a contained one — and they are the same declaration at
two altitudes. Carrying them separately meant every read, every rollup and
every rating path asked *which column is populated?* before it could ask
anything useful. A contained unit is **the same record with a parent** (#154
§3.1), so the parent link is the only thing that says which altitude a row sits
at, and one column says what kind of work it is.

**THE STATED REASON FOR DROPPING A COLUMN THAT MAY HOLD ROWS** (ADR-0007 §1):
the column holds a declaration the surviving column now holds instead, and the
`RunPython` above the drop carries every row's value onto it first. Nothing is
discarded — the fact moves.

**The reverse is exact, and it is the collapse's own premise that makes it so.**
Splitting the column back out needs to know which rows were contained work,
and `parent_id` answers that for every row — which is precisely the claim this
migration rests on. A reverse that had to guess would have been the sign the
collapse was lossy.

⚠ **Both columns populated on one row is a shape no writer produces**, and the
carry refuses it rather than choosing a winner: the two would be disagreeing
about one fact, and picking either silently is how a wrong answer becomes
permanent. Stating the premise here is cheaper than trusting it.
"""
from django.db import migrations, models


def carry_the_contained_kind_onto_the_one_column(apps, schema_editor):
    Task = apps.get_model("work", "Task")
    disagreeing = (Task.objects.exclude(task_type="")
                   .exclude(subtask_type="").count())
    if disagreeing:
        raise RuntimeError(
            f"{disagreeing} unit(s) of work declare a kind in BOTH type "
            f"columns. The two were written exclusively, so this shape has no "
            f"writer; carrying either one would silently discard the other's "
            f"claim about the same fact.")
    # `.update()` rather than a loop over saved instances: this is one
    # statement over the rows that have something to carry, and the live
    # model's own immutability guard is not the historical model's anyway.
    Task.objects.filter(task_type="").exclude(subtask_type="").update(
        task_type=models.F("subtask_type"))


def split_the_contained_kind_back_out(apps, schema_editor):
    Task = apps.get_model("work", "Task")
    Task.objects.filter(parent__isnull=False).exclude(task_type="").update(
        subtask_type=models.F("task_type"), task_type="")


class Migration(migrations.Migration):

    dependencies = [
        ("work", "0015_the_unit_total_counts_what_it_could_not_price"),
    ]

    operations = [
        migrations.RunPython(carry_the_contained_kind_onto_the_one_column,
                             split_the_contained_kind_back_out),
        migrations.RemoveField(model_name="task", name="subtask_type"),
    ]
