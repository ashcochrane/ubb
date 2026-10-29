"""The event_types app's database rules: the triggers no model declaration can hold.

Part of the fresh initial set the cutover regenerated (#190; ADR-0026). The schema
migration beside this one is generated from the final models; these rules are not
in Django's migration state, so they are carried here by hand. Each one is the
final installed definition the old migration chain left, carried exactly: the
function bodies are byte-for-byte the last installer's, and the refusal texts,
vocabulary literals and SQL aliases that tests compare are unchanged. Each
constant names the historical migration whose text it carries.

Every rule refuses with SQLSTATE 23000. Each statement is passed to `RunSQL` as a
list item so it runs verbatim — a plain string would be split and comment-stripped
by `sqlparse`, which would change the stored function bodies.

DEPENDENCIES (§0.3 point 1): this migration depends on the schema leaf of every
app owning a table its SQL references, never on an assumed `0001`:
  trg_event_type_keeps_its_held_names: ubb_event_type (event_types), ubb_quarantined_key (event_types)
"""
from django.db import migrations


#: A declaration is not deleted from under its held names (a deferred constraint trigger).
#: Carried from event_types/0011_a_declaration_is_not_deleted_from_under_its_held_names.
EVENT_TYPE_KEEPS_ITS_HELD_NAMES = """
CREATE FUNCTION ubb_event_type_keeps_its_held_names() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE CONSTRAINT TRIGGER trg_event_type_keeps_its_held_names
AFTER DELETE ON ubb_event_type
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION ubb_event_type_keeps_its_held_names();
"""


def _uninstall(trigger, table, function):
    return f"DROP TRIGGER {trigger} ON {table};\nDROP FUNCTION {function}();"


class Migration(migrations.Migration):

    dependencies = [
        ("event_types", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            [EVENT_TYPE_KEEPS_ITS_HELD_NAMES],
            [_uninstall("trg_event_type_keeps_its_held_names", "ubb_event_type", "ubb_event_type_keeps_its_held_names")],
        ),
    ]
