"""The usage row and its table take the canonical noun (#269, slice 2).

`UsageEvent` becomes `Posting` and `ubb_usage_event` becomes `ubb_posting`, so
the database stops preserving obsolete terminology (ADR-0006 §9, enforced by G9
in `apps/platform/tests/test_model_naming.py`). `Refund.usage_event` — the one
foreign key pointing in — is renamed with it.

**Hand-written, and it had to be.** `makemigrations` run non-interactively does
not ask "did you rename this?": it emits a `CreateModel`, a `DeleteModel` and a
field add-plus-remove, which builds an empty table beside a full one and drops
the original, taking every row with it. ADR-0007 §1 refuses that and the
pre-squash exemption is spent.

**The three operations, in this order and no other.**

`RenameModel` is a state-only move here. Both the old and the new state name the
table explicitly and neither has changed yet, so `alter_db_table` sees old and
new as equal and emits nothing — including for the inbound foreign key, whose
target table is still `ubb_usage_event` at that point. Doing it this way round
is what keeps Django from re-pointing `ubb_refund`'s constraint by dropping and
re-adding it.

`AlterModelTable` then issues `ALTER TABLE ... RENAME TO ...`, which Postgres
performs in place: the rows, the primary key, every foreign key pointing in, the
indexes, the constraints and the sequences all follow the table and keep their
identities. The `currency` column and its `usd` default ride along like any
other column (spec §K1–K2); nothing here touches the seven other currency
columns.

`RenameField` issues `ALTER TABLE ... RENAME COLUMN "usage_event_id" TO
"posting_id"`, which likewise carries the column's unique index and its foreign
key rather than rebuilding either.

**The constraint and index names are deliberately left alone.** They still spell
the retired noun — `uq_usage_event_idempotency_v2`, `idx_usage_*`. There is no
rename operation for a constraint, and Django can only drop and re-create one,
which is the add-plus-remove this migration exists to avoid, on a unique index
that is load-bearing while it is gone. #259 left its own alone for the same
reason. ADR-0006 §9's rule is about the table name.

The three `AlterField`s carry the reverse accessors (`related_name`) onto the
new noun. `related_name` is one of Django's non-database field attributes, so
none of them emits any SQL; they exist so the migration state matches the models
and `makemigrations --check` stays clean.

Reversible in full, and the reverse is exercised:
`usage/tests/test_posting_rename.py` renders this migration's SQL in both
directions and asserts it renames rather than rebuilds.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0001_initial"),
        ("tenants", "0022_tenantapikey_role"),
        ("usage", "0029_drop_rawingestevent"),
        ("work", "0001_initial"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="UsageEvent",
            new_name="Posting",
        ),
        migrations.AlterModelTable(
            name="posting",
            table="ubb_posting",
        ),
        migrations.RenameField(
            model_name="refund",
            old_name="usage_event",
            new_name="posting",
        ),
        migrations.AlterField(
            model_name="posting",
            name="tenant",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="postings",
                to="tenants.tenant",
            ),
        ),
        migrations.AlterField(
            model_name="posting",
            name="customer",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="postings",
                to="customers.customer",
            ),
        ),
        migrations.AlterField(
            model_name="posting",
            name="task",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="postings",
                to="work.task",
            ),
        ),
    ]
