"""The rate moves to the table named for a rate, and the kind word goes (#367).

Two corrections, one commit, and they are the same correction seen from two
sides.

**THE TABLE.** `Rate` — a single priced line — sat on `ubb_rate_card`, the name
that belongs to the container beside it, because the misnamed original took it
first and the container was pushed onto a suffixed spelling to make room. The
inversion has been recorded in the model's own docstring since `0010` and is
`gates/migration-ledger.yaml`'s G9 entry for this site. This is the rate half of
it. The container half is ticket 21's, and it is deliberately NOT taken here:
that ticket does not rename the container, it SPLITS it into a Pricing Book and
a cost book, so renaming it now and again there would be two renames of one
table to reach one name.

**THE KIND WORD.** A rate carried a `cost`/`price` discriminator copied from the
book it was created under. Nothing read it: resolution selects BOOKS by kind and
then asks this table for the rules inside them (`rate_card__in`), so the column
decided nothing while being free to disagree with the book it was copied from.
It is DELETED rather than re-spelled, which is the whole point of the slice —
one table wearing a kind word is what stopped the model saying that a book of
supplier costs and a book of customer prices are different things governed by
different rules (#148 §5.4). After this, no read of a rate asks it what kind it
is; the book it belongs to is the only thing that knows.

**ADR-0007 §1 GOVERNS THE SHAPE, AND `AlterModelTable` IS THE RENAME.** One
`ALTER TABLE ... RENAME TO` preserves every row, every index, every constraint
and — the part that is easy to assume rather than check — every TRIGGER, because
a trigger belongs to the table by identity rather than by name. This table
carries TWO: `trg_rate_declared_transitions` from `0018`, holding what may happen
to a rate's two effective moments, and `trg_rate_names_a_declaration` from
`0020`, holding which rates may be born at all. Both come across untouched and
both are asserted still installed and still refusing, through raw SQL, in
`test_a_rate_sits_on_the_table_named_for_a_rate.py`.

`usage/tests/test_posting_rename.py` names the three operations that are renames
rather than rebuilds — `AlterModelTable`, `RenameModel` and `RenameField` — and
the ones that cost rows. There is no `AddField` here and no `CreateModel`: the
one destructive operation is the deliberate deletion of the kind word, which is
a removal with nothing added to pair it with.

⚠ **HAND-WRITTEN, for the reason `0016` and `0026` both give.** `makemigrations`
only asks "did you rename this?" on a TTY, so a non-interactive run writes the
add-plus-remove pair ADR-0007 §1 forbids and does it silently. Nothing here was
generated.

**THE REVERSE PUTS THE WORD BACK WHERE THE OLD CODE WOULD READ IT.** Reversing
`RemoveField` alone would re-add the column at Django's empty-string default,
which is not a value any reader of it accepts — a rollback landing on rows whose
discriminator says nothing is the failure that makes an un-reversed data
migration worse than none (`0026`'s argument, applied to a deletion). So the
reverse re-derives each rate's kind from the book that holds it, which is where
the fact lives and has always lived. It runs after the column is back and before
the index over it is rebuilt, which is what its position in the list buys.

The migrations tree is a declared sweep exclusion
(`gates/forbidden-term-sweep.yaml`), so the retired word legitimately survives in
this file — which is the whole reason a rename migration is allowed to name what
it retires.
"""

from django.db import migrations, models

#: The kind word, spelled once, in the one file allowed to spell it: this is the
#: migration that deletes it, and a deletion that cannot name its subject is not
#: reviewable.
THE_KIND_COLUMN = "card_type"


def restore_the_kind_from_the_book(apps, schema_editor):
    """Reverse only — re-derive each rate's kind from the book that holds it.

    The fact is the book's and was only ever copied onto the rate, so this is a
    re-derivation rather than a restore from somewhere: there is nothing left on
    the rate to read. A rate attached to no book keeps the empty value, which is
    the state such a row would have had anyway — no route can produce one, and
    the backfill that created the books gave every existing rate one.
    """
    Rate = apps.get_model("pricing", "Rate")
    RateCard = apps.get_model("pricing", "RateCard")
    for kind in RateCard.objects.values_list(THE_KIND_COLUMN, flat=True).distinct():
        Rate.objects.filter(rate_card__isnull=False,
                            **{f"rate_card__{THE_KIND_COLUMN}": kind}).update(
            **{THE_KIND_COLUMN: kind})


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0026_the_rates_arithmetic_shape_takes_its_ratified_name'),
    ]

    operations = [
        # THE INDEX LED ON THE COLUMN BEING DELETED, so it comes off first —
        # Django's state may not hold an index over a field that is gone. It is
        # rebuilt at the bottom without that term and under a name that says
        # which table it is on, because an index named for the container on a
        # table named for a rate is the same wart one layer down.
        migrations.RemoveIndex(
            model_name='rate',
            name='idx_ratecard_lookup',
        ),
        # Forward: nothing. Reverse: the column is back by now and empty, and
        # this is what makes it readable again. See the module docstring.
        migrations.RunPython(migrations.RunPython.noop,
                             restore_the_kind_from_the_book),
        migrations.RemoveField(
            model_name='rate',
            name=THE_KIND_COLUMN,
        ),
        # THE RENAME. One statement, every row, both triggers.
        migrations.AlterModelTable(
            name='rate',
            table='ubb_rate',
        ),
        migrations.AddIndex(
            model_name='rate',
            index=models.Index(
                fields=['tenant', 'provider', 'event_type', 'measurement'],
                name='idx_rate_lookup'),
        ),
    ]
