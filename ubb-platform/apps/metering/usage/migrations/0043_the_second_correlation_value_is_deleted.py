"""The second caller-supplied correlation value is deleted (#411).

**A REMOVAL, AND ONLY A REMOVAL.** No column is added, nothing is renamed, and
no row moves. `request_id` leaves `ubb_posting`, and its `db_index=True` index
leaves with it.

**WHY IT IS SAFE TO DROP RATHER THAN CARRY.** The column had no uniqueness
constraint, no lookup, and no read that ever changed any behaviour (#179 §4).
It was written at insert and echoed back on two read schemas, and that was the
whole of its life: nothing filtered on it, nothing joined through it, no rule
keyed off it, and no `plpgsql` body names it — `0001_initial` is the only other
migration in the tree that spells it, as a column declaration. What it did cost
was an index write on the hottest path in the system, on every recorded event.

**WHY IT WAITED FOR SLICE 5 RATHER THAN GOING IN SLICE 2.** Deleting one of two
correlation values is only safe once the other one is load-bearing on its own.
`idempotency_key` became caller-supplied with a permanent claim in #410, the
ticket immediately before this one — it is what decides a replay, and it is now
the only correlation identity UBB has. `gates/migration-ledger.yaml` recorded
that ordering as the reason the debt was owned by this slice: *"the deletion is
safe only once the key that replaces it is finalised."*

**THIS IS A CONTRACT BREAK AND IT IS DELIBERATE.** The field was REQUIRED on
`POST /api/v1/metering/usage` and is published on the usage list row and the
usage detail row. A caller still sending it gets `200` and the key is dropped,
which is this repository's ratified posture for a retired wire field (#272,
argued at `api/v1/schemas.py`) rather than an oversight: this re-model renames
wire fields every slice, and a caller mid-migration must not be broken by each
one in turn. The break is recorded in `openapi/oasdiff-err-ignore.txt` from
`oasdiff`'s own output.

**NO DATA MIGRATION, AND THAT IS THE POINT.** There is nowhere to carry the
values to. A second name for a correlation is not a fact about the charge, and
the record that matters — what a tenant was charged and why — is the pricing
receipt, which never referenced this column. A tenant who wants their own
correlation string on an event has `metadata`, which is theirs to key.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("usage", "0042_the_receipt_takes_the_ratified_name_of_what_it_holds"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="posting",
            name="request_id",
        ),
    ]
