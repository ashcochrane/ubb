"""The pricing app's database rules: the triggers no model declaration can hold.

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
  trg_rate_declared_transitions: ubb_rate (pricing)
  trg_rate_names_a_declaration: ubb_rate (pricing)
  trg_book_publish_declared_transitions: ubb_pricing_book_publish (pricing)
  trg_resolution_run_is_never_edited: ubb_resolution_run (pricing)
  trg_charge_declared_transitions: ubb_charge (pricing)
  trg_task_price_declared_transitions: ubb_task_price (pricing)
"""
from django.db import migrations


#: A rate's validity window: `valid_from` is FROZEN and `valid_to` SET_ONCE.
#: Carried from pricing/0018_a_rate_takes_effect_from_the_moment_the_tenant_chooses, on the table pricing/0027 renamed to `ubb_rate`.
RATE_DECLARED_TRANSITIONS = """
CREATE FUNCTION ubb_rate_declared_transitions() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- valid_from is declared FROZEN: a rule's effective moment is a fact about
    -- the rule, and moving it re-costs work that has already reported.
    IF NEW.valid_from IS DISTINCT FROM OLD.valid_from THEN
        RAISE EXCEPTION
            'valid_from is declared frozen (ADR-0007 §2): when a rate took '
            'effect is a fact about the rate, and moving it re-costs work '
            'that has already reported; got % to %',
            OLD.valid_from, NEW.valid_from
            USING ERRCODE = '23000';
    END IF;

    -- valid_to is declared SET_ONCE: nothing to a moment, once. Opening the
    -- close again, or moving it, both land here; leaving it alone does not
    -- reach the function at all.
    IF NEW.valid_to IS DISTINCT FROM OLD.valid_to
       AND OLD.valid_to IS NOT NULL THEN
        RAISE EXCEPTION
            'valid_to is declared set_once (ADR-0007 §2): closing a rate is a '
            'one-way act, and reopening one over a period that has already '
            'reported rewrites history rather than editing it; got % to %',
            OLD.valid_to, NEW.valid_to
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_rate_declared_transitions
BEFORE UPDATE ON ubb_rate
FOR EACH ROW
WHEN (OLD.valid_from IS DISTINCT FROM NEW.valid_from
      OR OLD.valid_to IS DISTINCT FROM NEW.valid_to)
EXECUTE FUNCTION ubb_rate_declared_transitions();
"""

#: A new rate names the declared quantity it prices, or is refused.
#: Carried from pricing/0020_a_new_rate_names_a_declaration_or_is_refused, on the table pricing/0027 renamed to `ubb_rate`.
RATE_NAMES_A_DECLARATION = """
CREATE FUNCTION ubb_rate_names_a_declaration() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE TRIGGER trg_rate_names_a_declaration
BEFORE INSERT ON ubb_rate
FOR EACH ROW
WHEN (NEW.measurement_id IS NULL)
EXECUTE FUNCTION ubb_rate_names_a_declaration();
"""

#: A published book publish is never edited.
#: Carried from pricing/0023_every_change_to_a_book_is_a_publish.
BOOK_PUBLISH_DECLARED_TRANSITIONS = """
CREATE FUNCTION ubb_book_publish_declared_transitions() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- declaration_status is declared RESOLVE_ONCE, and this is the record rule
    -- that makes it so: a published record is what a decision did to a book on
    -- a day, and every column of it is fixed at that moment. A draft is
    -- untouched by this function -- the WHEN clause below never lets one in --
    -- which is what "freely editable, freely discardable" means.
    IF OLD.declaration_status = 'published' THEN
        RAISE EXCEPTION
            'declaration_status is declared resolve_once (ADR-0007 §2): a '
            'published pricing book publish records the decision that put a '
            'price in force, so no column of it moves afterwards -- including '
            'this one, which cannot return to draft; got status % to %',
            OLD.declaration_status, NEW.declaration_status
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_book_publish_declared_transitions
BEFORE UPDATE ON ubb_pricing_book_publish
FOR EACH ROW
WHEN (OLD.declaration_status = 'published')
EXECUTE FUNCTION ubb_book_publish_declared_transitions();
"""

#: A Resolution Run is recorded once and never edited.
#: Carried from pricing/0025_a_resolution_run_is_recorded_once_and_never_edited.
RESOLUTION_RUN_IS_NEVER_EDITED = """
CREATE FUNCTION ubb_resolution_run_is_never_edited() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'a resolution run is recorded once and never edited: it is the record '
        'of an irreversible act, and the only surviving explanation of the '
        'numbers it completed; a correction belongs in a record beside it'
        USING ERRCODE = '23000';
END;
$$;

CREATE TRIGGER trg_resolution_run_is_never_edited
BEFORE UPDATE ON ubb_resolution_run
FOR EACH ROW
EXECUTE FUNCTION ubb_resolution_run_is_never_edited();
"""

#: A Charge is written once and never edited.
#: Carried from pricing/0031_a_delivered_piece_of_work_is_charged_once.
CHARGE_DECLARED_TRANSITIONS = """
CREATE FUNCTION ubb_charge_declared_transitions() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    moved text[];
BEGIN
    -- Every economic column of a Charge is declared FROZEN: what UBB charged a
    -- customer, in which currency, against which line of which version of which
    -- book, and at which instants, are facts about a money movement that
    -- already happened. Correcting one is another row of this table naming it,
    -- never a rewrite of it.
    SELECT array_agg(changed.key ORDER BY changed.key) INTO moved
    FROM (
        SELECT after.key
        FROM jsonb_each(to_jsonb(NEW)) AS after(key, value)
        JOIN jsonb_each(to_jsonb(OLD)) AS before(key, value)
          ON before.key = after.key
        WHERE after.value IS DISTINCT FROM before.value
          AND after.key = ANY (ARRAY['tenant_id', 'task_id', 'amount_micros', 'currency', 'agreed_price_line_id', 'book_version', 'resolved_at', 'charged_at', 'idempotency_key', 'compensates_id', 'grouping_field_1', 'grouping_field_2', 'grouping_field_3', 'grouping_field_4', 'grouping_field_5', 'grouping_field_6', 'grouping_field_7', 'grouping_field_8', 'grouping_field_9', 'grouping_field_10'])
    ) AS changed;

    IF moved IS NOT NULL THEN
        RAISE EXCEPTION
            'these columns of ubb_charge are declared frozen (ADR-0007 2): '
            '%. A charge records money that already moved; correct it with a '
            'compensating record naming it, which leaves a trail, rather than '
            'by rewriting what it says.',
            array_to_string(moved, ', ')
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_charge_declared_transitions
BEFORE UPDATE ON ubb_charge
FOR EACH ROW
EXECUTE FUNCTION ubb_charge_declared_transitions();
"""

#: An agreed price's window is held by the database.
#: Carried from pricing/0032_an_agreed_price_is_published_with_provenance.
TASK_PRICE_DECLARED_TRANSITIONS = """
CREATE FUNCTION ubb_task_price_declared_transitions() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- valid_from is declared FROZEN: when an agreed price took effect is a
    -- fact about the line, and the publish that opened it says so.
    IF NEW.valid_from IS DISTINCT FROM OLD.valid_from THEN
        RAISE EXCEPTION
            'valid_from is declared frozen (ADR-0007 §2): when an agreed price '
            'took effect is a fact about the line its publish recorded, and '
            'moving it rewrites which price was in force; got % to %',
            OLD.valid_from, NEW.valid_from
            USING ERRCODE = '23000';
    END IF;

    -- valid_to is declared SET_ONCE: nothing to a moment, once. Reopening a
    -- line, or moving its close, both land here.
    IF NEW.valid_to IS DISTINCT FROM OLD.valid_to
       AND OLD.valid_to IS NOT NULL THEN
        RAISE EXCEPTION
            'valid_to is declared set_once (ADR-0007 §2): closing an agreed '
            'price is a one-way act, and reopening one rewrites history '
            'rather than editing it; got % to %',
            OLD.valid_to, NEW.valid_to
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_task_price_declared_transitions
BEFORE UPDATE ON ubb_task_price
FOR EACH ROW
WHEN (OLD.valid_from IS DISTINCT FROM NEW.valid_from
      OR OLD.valid_to IS DISTINCT FROM NEW.valid_to)
EXECUTE FUNCTION ubb_task_price_declared_transitions();
"""


def _uninstall(trigger, table, function):
    return f"DROP TRIGGER {trigger} ON {table};\nDROP FUNCTION {function}();"


class Migration(migrations.Migration):

    dependencies = [
        ("pricing", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            [RATE_DECLARED_TRANSITIONS],
            [_uninstall("trg_rate_declared_transitions", "ubb_rate", "ubb_rate_declared_transitions")],
        ),
        migrations.RunSQL(
            [RATE_NAMES_A_DECLARATION],
            [_uninstall("trg_rate_names_a_declaration", "ubb_rate", "ubb_rate_names_a_declaration")],
        ),
        migrations.RunSQL(
            [BOOK_PUBLISH_DECLARED_TRANSITIONS],
            [_uninstall("trg_book_publish_declared_transitions", "ubb_pricing_book_publish", "ubb_book_publish_declared_transitions")],
        ),
        migrations.RunSQL(
            [RESOLUTION_RUN_IS_NEVER_EDITED],
            [_uninstall("trg_resolution_run_is_never_edited", "ubb_resolution_run", "ubb_resolution_run_is_never_edited")],
        ),
        migrations.RunSQL(
            [CHARGE_DECLARED_TRANSITIONS],
            [_uninstall("trg_charge_declared_transitions", "ubb_charge", "ubb_charge_declared_transitions")],
        ),
        migrations.RunSQL(
            [TASK_PRICE_DECLARED_TRANSITIONS],
            [_uninstall("trg_task_price_declared_transitions", "ubb_task_price", "ubb_task_price_declared_transitions")],
        ),
    ]
