"""The code_builder app's database rules: the triggers no model declaration can hold.

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
  trg_blueprint_snapshot_declared_transitions: ubb_blueprint_snapshot (code_builder)
"""
from django.db import migrations


#: A resolved Blueprint keeps its content.
#: Carried from code_builder/0001_a_resolved_blueprint_keeps_its_content.
BLUEPRINT_SNAPSHOT_DECLARED_TRANSITIONS = """
CREATE FUNCTION ubb_blueprint_snapshot_declared_transitions() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- tenant_id, configuration_fingerprint and content are declared FROZEN:
    -- the fingerprint is the hash of the content, and a generated file was
    -- stamped with it. A snapshot is replaced by resolving again, which
    -- stores a new one beside it.
    IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
       OR NEW.configuration_fingerprint IS DISTINCT FROM OLD.configuration_fingerprint
       OR NEW.content IS DISTINCT FROM OLD.content THEN
        RAISE EXCEPTION
            'tenant_id, configuration_fingerprint and content are declared '
            'frozen (ADR-0007 §2): a blueprint snapshot is the content its '
            'fingerprint is the hash of, and it never changes; resolve the '
            'blueprint again instead'
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_blueprint_snapshot_declared_transitions
BEFORE UPDATE ON ubb_blueprint_snapshot
FOR EACH ROW
WHEN (OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
      OR OLD.configuration_fingerprint IS DISTINCT FROM NEW.configuration_fingerprint
      OR OLD.content IS DISTINCT FROM NEW.content)
EXECUTE FUNCTION ubb_blueprint_snapshot_declared_transitions();
"""


def _uninstall(trigger, table, function):
    return f"DROP TRIGGER {trigger} ON {table};\nDROP FUNCTION {function}();"


class Migration(migrations.Migration):

    dependencies = [
        ("code_builder", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            [BLUEPRINT_SNAPSHOT_DECLARED_TRANSITIONS],
            [_uninstall("trg_blueprint_snapshot_declared_transitions", "ubb_blueprint_snapshot", "ubb_blueprint_snapshot_declared_transitions")],
        ),
    ]
