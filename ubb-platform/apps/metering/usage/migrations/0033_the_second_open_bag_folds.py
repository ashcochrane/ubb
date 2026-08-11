"""The posting's second open bag folds into the first (#273).

A MOVE, NOT A RETIREMENT, and the distinction is the whole ruling — the mirror
of #272's. That column dropped because there was nowhere to carry it to. This
one has somewhere: the posting already carries an open bag, and the second one
duplicated it under a name that advertised a capability the survivor
deliberately does not have. An unbounded free-text keyspace that can become a
chart is an unbounded free-text keyspace that can drive an invoice line label,
and that is the capability the retiring name promised. **The tenant's data is
not what is being retired**, so ADR-0007 §1's rule — *a migration that moves a
column carries its data* — governs, and the fold below is what carries it.

Why the fold can refuse
-----------------------
Two bags merging into one keyspace can collide, and a collision is the one case
where a merge silently destroys a value. UBB cannot pick a winner on the
tenant's behalf: the two bags disagreed about one key and only the tenant knows
which answer was meant. So the fold **raises**, naming the posting and the key,
rather than choosing. A key present in both with the *same* value is not a
collision — nothing is lost by merging it, and it is merged.

No row can trip this today: nothing in this repository writes both bags with
overlapping keys, and UBB is not deployed. The guard exists so that if that ever
stops being true the failure is loud at migration time rather than silent in an
invoice.

Why the reverse duplicates rather than guesses
----------------------------------------------
Once the two keyspaces are one, which key came from which bag is genuinely gone
— nothing records it and nothing could without polluting the tenant's own
keyspace with provenance they did not author. A reverse that invented a split
would be guessing at the tenant's data.

So the reverse gives **both** bags the merged contents. Nothing is lost in
either direction, the reverse is not a `noop` dressed up as one, and the round
trip is total: folding a reversed fold merges each key with itself, which is the
equal-value case the guard above permits. `tests/test_the_second_open_bag_folds.py`
runs all three legs against a real database.

The index moves with the filtering
----------------------------------
Filtering is what survives the fold (grouping is slice 7's to migrate onto its
declared grouping contract), and filtering on a JSON bag without a GIN index is
a sequential scan of the largest table in the system. 0022 put a `jsonb_ops` GIN
index on the retiring column for exactly the containment and key-exists lookups
that now run against the survivor, so the survivor gets one — this time declared
on the model, inside Django's state, rather than as the raw SQL 0022 had to use
to swap opclasses concurrently.

**The retiring column's own index leaves with the column and the reverse does not
bring it back.** It was created by `RunPython` in 0022 and never entered Django's
migration state, so no operation here owns it; reversing to 0022 is what restores
it. Recorded rather than left to be discovered from a slow query.
"""

from django.db import migrations
import django.contrib.postgres.indexes


def fold_the_second_bag_into_the_first(apps, schema_editor):
    """Every key in the retiring bag joins the surviving one.

    The surviving bag wins a same-key, same-value tie by being written last;
    a same-key, *different*-value pair is refused above rather than resolved.
    `bulk_update` rather than `save()`: the posting's save guard refuses any
    non-adding write, and a historical model would not carry it anyway.
    """
    Posting = apps.get_model("usage", "Posting")
    batch = []
    for posting_id, retiring, surviving in Posting.objects.exclude(
            tags__isnull=True).values_list(
                "id", "tags", "metadata").iterator(chunk_size=1000):
        retiring = retiring or {}
        surviving = surviving or {}
        for key, value in retiring.items():
            if key in surviving and surviving[key] != value:
                raise ValueError(
                    f"posting {posting_id} carries key {key!r} in both open "
                    f"bags with different values ({value!r} and "
                    f"{surviving[key]!r}). The fold will not pick a winner on "
                    f"the tenant's behalf — decide which value survives, write "
                    f"it into both bags, and re-run.")
        batch.append(Posting(pk=posting_id, metadata={**retiring, **surviving}))
        if len(batch) == 1000:
            Posting.objects.bulk_update(batch, ["metadata"])
            batch = []
    if batch:
        Posting.objects.bulk_update(batch, ["metadata"])


def unfold_the_bag_into_two_copies(apps, schema_editor):
    """Both bags get the merged contents; neither gets a guess.

    An empty bag reverses to NULL rather than to `{}` — NULL is what the
    restored column meant before the fold for a posting that carried no labels,
    and `{}` would claim the tenant authored an empty bag.
    """
    Posting = apps.get_model("usage", "Posting")
    batch = []
    for posting_id, surviving in Posting.objects.values_list(
            "id", "metadata").iterator(chunk_size=1000):
        batch.append(Posting(pk=posting_id, tags=dict(surviving) or None))
        if len(batch) == 1000:
            Posting.objects.bulk_update(batch, ["tags"])
            batch = []
    if batch:
        Posting.objects.bulk_update(batch, ["tags"])


class Migration(migrations.Migration):

    dependencies = [
        ('usage', '0032_the_inline_unit_total_dies'),
    ]

    operations = [
        migrations.RunPython(fold_the_second_bag_into_the_first,
                             unfold_the_bag_into_two_copies),
        migrations.RemoveField(
            model_name='posting',
            name='tags',
        ),
        migrations.AddIndex(
            model_name='posting',
            index=django.contrib.postgres.indexes.GinIndex(
                fields=['metadata'], name='idx_posting_metadata'),
        ),
    ]
