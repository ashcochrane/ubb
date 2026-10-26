"""A declaration is not deleted from under the names held beneath it (#473 row 3).

**The rule, as the owner ruled it (2026-10-22): deletion is refused while held
names depend on it.** A quantity held because a declared Event Type does not
carry its name waits on the tenant deciding what that name meant — map it to a
quantity the declaration carries, register it, or dismiss it — and every one of
those answers is about THAT declaration. Deleting it leaves the held row open
with nothing to resolve it against, and before #568 it did worse: a Resolution
Run re-costing the event found no declaration and rated the held name by its
spelling.

**A database rule, because a deletion has every door.** No route deletes an
Event Type, so what deletes one is the ORM — an instance, a queryset, raw SQL —
and a model-level `delete()` guard would hold only the first (ADR-0007 §2: a
model-level rule is a courtesy to the ordinary path, never the enforcement).

**Deferred to the end of the transaction, and asked of what is LEFT, which is
what keeps it from refusing the deletions that are fine.** A tenant's own
deletion takes its Event Types and its held names in one transaction, in
whatever order Django's collector picks; asked row by row, the rule would refuse
it whenever the Event Type happened to go first. Asked at commit, the held names
have gone too. And a transaction that deletes an Event Type and declares the
same key again has left the held names a declaration to be answered against, so
the rule asks whether ANY Event Type holds the key by then — not whether this
one row survived.

**Only a held QUANTITY depends on its Event Type.** An unrecognised Event Type
is held precisely because no publication answers its key, so a draft at that
key is nothing it depends on, and deleting the draft leaves every remediation
open to it. A held name already decided depends on nothing: its decision is
recorded on its own row, by key (`QuarantinedKey.resolved_key` is a key and
never a relation, so a decision from two years ago cannot refuse a deletion on
behalf of a typo — this rule is about names still waiting).

SQLSTATE `23000`, the family every rule on these tables answers with, so the ORM
raises `IntegrityError`. The reverse drops the trigger and the function.
"""
from django.db import migrations

TRIGGER = "trg_event_type_keeps_its_held_names"
FUNCTION = "ubb_event_type_keeps_its_held_names"

#: Frozen, for the reason `usage/0036` gives: a migration records the schema
#: as it was on the day it ran. `measurement_key` is the unrecognised kind a
#: quantity is held as, and `''` is the resolution a still-held row carries.
INSTALL = f"""
CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    waiting integer;
BEGIN
    IF EXISTS (SELECT 1 FROM ubb_event_type e
               WHERE e.tenant_id = OLD.tenant_id AND e.key = OLD.key) THEN
        RETURN NULL;
    END IF;
    SELECT count(*) INTO waiting FROM ubb_quarantined_key q
     WHERE q.tenant_id = OLD.tenant_id
       AND q.event_type_key = OLD.key
       AND q.unrecognised = 'measurement_key'
       AND q.resolution = '';
    IF waiting > 0 THEN
        RAISE EXCEPTION
            'Event Type % cannot be deleted while % held name(s) beneath it '
            'are undecided (#473): each waits on the tenant mapping it to a '
            'quantity this declaration carries, registering it, or dismissing '
            'it as non-economic, and a deleted declaration leaves none of '
            'those to answer against. Decide them first.',
            OLD.key, waiting
            USING ERRCODE = '23000';
    END IF;
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER {TRIGGER}
AFTER DELETE ON ubb_event_type
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION {FUNCTION}();
"""

REMOVE = f"""
DROP TRIGGER {TRIGGER} ON ubb_event_type;
DROP FUNCTION {FUNCTION}();
"""


def install(apps, schema_editor):
    schema_editor.execute(INSTALL, params=None)


def remove(apps, schema_editor):
    schema_editor.execute(REMOVE, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ("event_types", "0010_a_held_name_names_the_event_it_arrived_on"),
    ]

    operations = [
        migrations.RunPython(install, remove),
    ]
