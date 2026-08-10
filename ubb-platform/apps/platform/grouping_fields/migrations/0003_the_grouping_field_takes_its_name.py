"""The two records and their two tables take the canonical noun (#259, slice 2).

`DimensionDef` becomes `GroupingField` and `DimensionValue` becomes
`GroupingFieldValue`, and both tables are renamed to track them (ADR-0006 §9,
enforced by G9 in `apps/platform/tests/test_model_naming.py`).

**Hand-written, and it had to be.** `makemigrations` run non-interactively does
not ask "did you rename this?" — it emits two `CreateModel`s, four constraint
and index drops, four adds, and two `DeleteModel`s. That is an add-plus-remove:
it builds empty tables beside the full ones and drops the originals, taking
every row with them. ADR-0007 §1 refuses it and this ticket names it explicitly.

`RenameModel` plus `AlterModelTable` is a rename in the database's own terms.
`RenameModel` is a state-only move here, because both tables are named
explicitly and the name has not changed yet, so its `alter_db_table` sees old
and new as equal and emits nothing. `AlterModelTable` then issues
`ALTER TABLE ... RENAME TO ...`, which Postgres performs in place: the rows, the
primary key, every foreign key pointing in, the indexes, the constraints and the
sequences all follow the table and keep their identities.

**The constraint and index names are deliberately left alone.** They still spell
the retired noun. There is no rename operation for a constraint — Django can only
drop and re-create one, which is the add-plus-remove this migration exists to
avoid, on a unique index that is load-bearing while it is gone. ADR-0006 §9's
rule is about the table name, and the tables now track their models.

The two `AlterField`s carry the reverse accessors (`related_name`) onto the new
model names. `related_name` is one of Django's non-database field attributes, so
neither emits any SQL; they exist so the migration state matches the models and
`makemigrations --check` stays clean.

Reversible in full, and the reverse is exercised:
`grouping_fields/tests/test_app_label_move.py` renders this migration's SQL in
both directions and asserts it renames rather than rebuilds.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    # 0002 re-labels the content types BEFORE the renames below, because
    # `contenttypes` injects its own `RenameContentType` after each
    # `RenameModel` and looks the row up under the new app label.
    dependencies = [
        ("tenants", "0022_tenantapikey_role"),
        ("grouping_fields", "0002_rename_app_label_content_types"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="DimensionDef",
            new_name="GroupingField",
        ),
        migrations.RenameModel(
            old_name="DimensionValue",
            new_name="GroupingFieldValue",
        ),
        migrations.AlterModelTable(
            name="groupingfield",
            table="ubb_grouping_field",
        ),
        migrations.AlterModelTable(
            name="groupingfieldvalue",
            table="ubb_grouping_field_value",
        ),
        migrations.AlterField(
            model_name="groupingfield",
            name="tenant",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="grouping_fields",
                to="tenants.tenant",
            ),
        ),
        migrations.AlterField(
            model_name="groupingfieldvalue",
            name="tenant",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="grouping_field_values",
                to="tenants.tenant",
            ),
        ),
    ]
