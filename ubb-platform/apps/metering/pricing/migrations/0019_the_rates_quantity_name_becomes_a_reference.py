"""The rate's quantity name becomes a reference to the declaration (#326).

`0016` renamed this column and said, in its own prose and in the model's, that
slice 2 was paying the WORD and slice 3 would pay the referential integrity:
*"making the last of them refusable is slice 3's"*. This is that migration. A
rate now names the declared record rather than a spelling of it, so a typo
cannot sit on a rate costing nothing and looking configured.

**A REPRESENTATION MOVE, HAND-ORDERED — ADR-0007 §1.** Create the reference,
carry the data, then drop the text. The autodetector writes the opposite for
this shape and does it silently: run without a terminal it never asks *"did you
rename this?"*, and an `AddField` beside a `RemoveField` produces a column of
the right name holding none of the data, which every test asking only whether
the new field exists would pass straight over. G20 is `owned_by_slice_8` and
does not gate this yet, so the ordering below is held by
`pricing/tests/test_a_rate_names_a_declared_quantity.py` rather than by a gate.

**THE TWO DATABASE OBJECTS OVER THE COLUMN ARE REWRITTEN, NOT CARRIED.** A
rename can leave `idx_ratecard_lookup` and `uq_rate_active_in_book` alone —
Postgres rewrites their definitions under it, which is why `0016`'s database
half was empty. This move cannot: they are built over a column that ceases to
exist, so both are dropped and rebuilt over the reference. Each still enforces
what it enforced before, and the unique one only does so because the lookup that
resolves a name to a declaration is deterministic — see
`apps/platform/event_types/quantities.py`.

**THE ORDER IS CHOSEN FOR THE REVERSE, WHICH IS THE HALF THAT IS EASY TO GET
WRONG.** The two objects are dropped FIRST, before the backfill, so that going
backwards they are rebuilt LAST — after the reverse has put the names back. Built
in the obvious order instead, the reverse would rebuild a partial unique index
over a column every row had just been given the same empty string in, and a
migration that cannot reverse on the data it created is not reversible in any
sense a tenant benefits from.

**A ROW NAMING A QUANTITY NO DECLARATION MATCHES IS DEACTIVATED.** Not deleted
and not repointed: deleting it destroys the evidence a tenant needs to fix it,
and repointing it at some other declaration invents a decision the tenant never
made. It keeps its row, it keeps its name in `undeclared_measurement_key` —
which is what it answers with, and what the reverse reads to put the text column
back exactly as it found it — and it references nothing, so nothing resolves
against it. `ck_rate_names_one_quantity` makes that the ONLY state a
reference-less rate may be in: it must carry the name, and it may not carry both.

⚠ **That check is not what stops the null being a door — `0020` is.** A check
cannot tell an INSERT from an UPDATE, so it is satisfied by a rate INSERTED with
no reference and a loose name, which is precisely the defect this migration
exists to delete. The trigger beside it refuses that insert; the two rules are
described together where the second is installed.

⚠ **The rebuilt unique constraint does not cover the deactivated rows**, and
that is a real difference rather than an oversight. Postgres treats NULLs as
distinct, so two placeless rows with identical selectors no longer collide where
two rows holding the same text did. Nothing can produce a second one — the only
writer of that state is this migration, and `0020` refuses the insert — so the
population is closed at whatever the conversion found. Recorded because "still
enforces what it enforced before" is otherwise not literally true.

**The quantity's published name does not move.** `measurement_key` is still what
the three rate schemas carry, still what the receipt and the audit record write,
and still a string: it is now derived from the declaration rather than stored
beside it. The one contract change in this commit is elsewhere and is additive —
withdrawing a declaration a rate prices answers 409, because `PROTECT` would
otherwise surface as a 500.
"""

import django.db.models.deletion
from django.db import migrations, models

#: One statement per thousand rows rather than one per row, on a table that
#: holds every priced rule a tenant has ever written.
BATCH = 1000


def _flush(Rate, batch, columns):
    """`bulk_update` rather than `save()`.

    The transition trigger `0018` installs is `BEFORE UPDATE` with a `WHEN`
    clause naming `valid_from` and `valid_to`, and neither column is written
    here — so these statements never enter it. That is not luck: a data
    migration is one of the doors that trigger exists to cover, and a backfill
    that had to move an effective moment to do its job would be refused by it.
    """
    if batch:
        Rate.objects.bulk_update(batch, columns, batch_size=BATCH)


def point_each_rate_at_its_declaration(apps, schema_editor):
    """Every rate takes the record its name is the name of, or keeps the name.

    The declarations are read into one map rather than queried per rate: a
    tenant's whole catalogue is small, the rate table is not, and one query per
    rate over a table with no index on this pair is how a backfill becomes an
    outage.

    THE EARLIEST DECLARATION WINS, matching `quantities.declaration_named`.
    Declarations are Event-Type-local, so a tenant may carry one name under
    several Event Types; resolution has always matched on the name and still
    does, so which one is referenced changes nothing a rate prices — and picking
    the same one here as the live lookup picks is what keeps the rebuilt unique
    constraint refusing the pair it refused before.
    """
    Rate = apps.get_model("pricing", "Rate")
    Measurement = apps.get_model("event_types", "Measurement")

    declared = {}
    for tenant_id, code, declaration_id in (
            Measurement.objects.order_by("created_at", "id")
            .values_list("event_type__tenant_id", "code", "id")):
        declared.setdefault((tenant_id, code), declaration_id)

    placed, deactivated = [], []
    for rate in Rate.objects.iterator(chunk_size=BATCH):
        declaration_id = declared.get((rate.tenant_id, rate.measurement_key))
        if declaration_id is None:
            rate.undeclared_measurement_key = rate.measurement_key
            deactivated.append(rate)
            if len(deactivated) == BATCH:
                _flush(Rate, deactivated, ["undeclared_measurement_key"])
                deactivated = []
        else:
            rate.measurement_id = declaration_id
            placed.append(rate)
            if len(placed) == BATCH:
                _flush(Rate, placed, ["measurement"])
                placed = []
    _flush(Rate, placed, ["measurement"])
    _flush(Rate, deactivated, ["undeclared_measurement_key"])


def restore_the_name_as_text(apps, schema_editor):
    """The name goes back as text, from whichever of the two columns holds it.

    A rate that was placed answers with its declaration's code; a rate that was
    deactivated answers with the name this migration preserved for exactly this
    purpose. Reversing a move must not be the one path that loses the data
    (`usage/migrations/0031`), and the deactivated rows are where that is easy
    to lose: their name is in neither the reference nor the column the forward
    pass emptied.
    """
    Rate = apps.get_model("pricing", "Rate")
    batch = []
    for rate in (Rate.objects.select_related("measurement")
                 .iterator(chunk_size=BATCH)):
        rate.measurement_key = (rate.undeclared_measurement_key
                                if rate.measurement_id is None
                                else rate.measurement.code)
        batch.append(rate)
        if len(batch) == BATCH:
            _flush(Rate, batch, ["measurement_key"])
            batch = []
    _flush(Rate, batch, ["measurement_key"])


class Migration(migrations.Migration):

    dependencies = [
        ('event_types', '0006_reported_cost_mapping'),
        ('pricing', '0018_a_rate_takes_effect_from_the_moment_the_tenant_chooses'),
    ]

    operations = [
        # 1. The two objects built over the text column go first, so that in
        #    reverse they are rebuilt last — after the names are back.
        migrations.RemoveIndex(
            model_name='rate',
            name='idx_ratecard_lookup',
        ),
        migrations.RemoveConstraint(
            model_name='rate',
            name='uq_rate_active_in_book',
        ),
        # 2. The reference, and the column that holds a name nothing matched.
        migrations.AddField(
            model_name='rate',
            name='measurement',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='rates', to='event_types.measurement'),
        ),
        migrations.AddField(
            model_name='rate',
            name='undeclared_measurement_key',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        # 3. The data, in both directions.
        migrations.RunPython(point_each_rate_at_its_declaration,
                             restore_the_name_as_text),
        # 4. The same two objects over the reference, plus the check that makes
        #    a rate name its quantity exactly once.
        migrations.AddIndex(
            model_name='rate',
            index=models.Index(
                fields=['tenant', 'card_type', 'provider', 'event_type',
                        'measurement'],
                name='idx_ratecard_lookup'),
        ),
        migrations.AddConstraint(
            model_name='rate',
            constraint=models.UniqueConstraint(
                condition=models.Q(('valid_to__isnull', True)),
                fields=('rate_card', 'measurement', 'currency', 'provider',
                        'event_type', 'task_type', 'subtask_type',
                        'grouping_field_1', 'grouping_field_2',
                        'grouping_field_3', 'grouping_field_4',
                        'grouping_field_5', 'grouping_field_6',
                        'grouping_field_7', 'grouping_field_8',
                        'grouping_field_9', 'grouping_field_10'),
                name='uq_rate_active_in_book'),
        ),
        migrations.AddConstraint(
            model_name='rate',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(('measurement__isnull', False),
                             ('undeclared_measurement_key', ''))
                    | (models.Q(('measurement__isnull', True))
                       & models.Q(('undeclared_measurement_key', ''),
                                  _negated=True))),
                name='ck_rate_names_one_quantity'),
        ),
        # 5. And only now the text.
        migrations.RemoveField(
            model_name='rate',
            name='measurement_key',
        ),
    ]
