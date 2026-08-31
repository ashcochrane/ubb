"""The version of the book that answered is pinned beside the price and the
line that produced it (#416, #139 §2.3).

`0022` pinned two of the three things that make an agreed price reproducible
from the record: the amount, and the identity of the line that answered. The
third is which published version of the customer's book held that line, and it
is added here because #416's Charge is required to carry it and this is the
only moment it is knowable.

**A BOOK'S VERSION COUNTER MOVES, WHICH IS THE WHOLE REASON THIS IS A COLUMN.**
`book_service.publish` steps `PricingBook.version` on every publish, so reading
it at any later moment — when the work closes, when a charge is written, when a
report is run — answers *the version this book is at now*. That is a number with
nothing to do with the resolution it would be recording. The line's own
`Rate.book_version_from` one table over does not answer it either: that says
which version OPENED a row, not which version the customer's book stood at when
the start gate read it.

**THE PAIR RULE WIDENS TO THREE RATHER THAN GAINING A NEIGHBOUR.** The amount,
the line and the version are one record of one resolution — a version with no
amount would describe a resolution that never happened, and an amount with no
version cannot say which published state of the book produced it. Beyond being
the truer statement, a FOURTH rule on this table would let one row break two at
once, which is exactly what the third one cost #415: four of its own refusal
assertions began naming a rule they had not driven, because the new rule fired
first and its message named itself. So this replaces
`ck_task_agreed_price_and_its_line_move_together` in place, and the table still
carries three checks and one trigger.

**PURE ADDITION FOR EVERY EXISTING ROW.** The column is nullable and every row
written before this commit has all three of the group null or — for a unit of
work started under `0022` and still running — an amount and a line with no
version. The second shape is admitted by the new check only in the sense that it
would not be, which is why this migration is safe on an EMPTY table and this
repository is deployed nowhere: there is no such row anywhere, and the
constraint is validated against the table as it stands.

**THE REVERSE IS EXACT**: restore the pair rule, drop the column. Nothing is
moved and nothing is rewritten.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0022_an_agreed_price_is_pinned_before_the_work_runs'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='task',
            name='ck_task_agreed_price_and_its_line_move_together',
        ),
        migrations.AddField(
            model_name='task',
            name='agreed_price_book_version',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name='task',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(agreed_price_micros__isnull=True,
                             agreed_price_line_id__isnull=True,
                             agreed_price_book_version__isnull=True)
                    | models.Q(agreed_price_micros__isnull=False,
                               agreed_price_line_id__isnull=False,
                               agreed_price_book_version__isnull=False)),
                name='ck_task_agreed_price_and_its_provenance_move_together'),
        ),
    ]
