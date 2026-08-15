"""A rate written from now on names a declaration, or is refused (#326).

`0019` made the reference nullable, because the rows it could not place have to
keep their place — and `ck_rate_names_one_quantity` was written to stop that null
being a way around the refusal. **It does not, and review found it.** The check
says a row referencing nothing must carry a name; so
`Rate.objects.create(tenant=t, undeclared_measurement_key="typo")` satisfies it
and writes exactly the defect this slice exists to delete: a rate naming a
quantity nobody declared, matching nothing, costing nothing, looking configured.
The database refused a rate with NO name. It did not refuse a rate with an
UNDECLARED one, and only the HTTP route did.

**This is the rule the check could not state.** A check is evaluated against one
row and cannot tell an INSERT from an UPDATE — and the difference is the whole
of it: the deactivated rows are UPDATED into existence by `0019`'s backfill, and
what must be refused is a rate INSERTED that way afterwards. A `BEFORE INSERT
... FOR EACH ROW` trigger sees exactly that difference, fires for every door —
`save()`, `bulk_create`, raw SQL, a later data migration — and refuses before the
write rather than unwinding one. `0018` on this table argues the mechanism at
length for the transition classes; this is the same mechanism for a different
question.

**The two rules are not the same rule said twice.** The check holds the SHAPE of
a row at all times: exactly one of the reference and the loose name says which
quantity a rate prices, never both and never neither, including across an update
that tries to blank a deactivated row's name. This trigger holds WHO MAY BE
BORN: nothing inserted after the conversion may reference nothing, whatever it
carries beside it. Take either away and a real write gets through.

**Inserts on the recording path pay nothing** — rates are read there, never
written. What pays is declaring a rate, which is a human changing a price, and
what it pays is one comparison against NULL.

**The refusal is raised as SQLSTATE 23000**, `integrity_constraint_violation`,
the class Django maps to `IntegrityError` — the same exception this table's
partial unique index, its check and `0018`'s trigger all raise. Three mechanisms
now answer with one exception type, so "the write was rejected" is not evidence
of anything: every test of this one asserts its MESSAGE.

**The reverse is real and a test runs it.** Dropping the trigger and its function
returns the table to what `0019` left. Nothing has to be unpicked because nothing
was written: this migration adds no column and moves no row.
"""

from django.db import migrations

TRIGGER = "trg_rate_names_a_declaration"
FUNCTION = "ubb_rate_names_a_declaration"

INSTALL = f"""
CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'a rate prices a declared quantity (#326): % is not one this tenant '
        'has declared, so there is nothing for the rate to name. Declare it '
        'on an Event Type first, then price it. Only the rows the conversion '
        'could not place may reference no declaration, and they are not '
        'written, they are what was already there',
        coalesce(nullif(NEW.undeclared_measurement_key, ''), '(no quantity)')
        USING ERRCODE = '23000';
END;
$$;

CREATE TRIGGER {TRIGGER}
BEFORE INSERT ON ubb_rate_card
FOR EACH ROW
WHEN (NEW.measurement_id IS NULL)
EXECUTE FUNCTION {FUNCTION}();
"""

UNINSTALL = f"""
DROP TRIGGER {TRIGGER} ON ubb_rate_card;
DROP FUNCTION {FUNCTION}();
"""


def install(apps, schema_editor):
    schema_editor.execute(INSTALL, params=None)


def uninstall(apps, schema_editor):
    schema_editor.execute(UNINSTALL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0019_the_rates_quantity_name_becomes_a_reference'),
    ]

    operations = [
        migrations.RunPython(install, uninstall),
    ]
