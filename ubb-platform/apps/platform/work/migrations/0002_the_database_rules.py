"""The work app's database rules: the triggers no model declaration can hold.

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
  trg_task_type_declared_transitions: ubb_task_type (work)
  trg_task_containment_shares_the_pricing_regime: ubb_task (work)
  trg_task_declared_transitions: ubb_task (work)
"""
from django.db import migrations


#: A kind of work's pricing regime is frozen.
#: Carried from work/0021_a_kind_of_work_declares_how_it_is_sold.
TASK_TYPE_DECLARED_TRANSITIONS = """
CREATE FUNCTION ubb_task_type_declared_transitions() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- pricing_mode is declared FROZEN: how a kind of work is sold is a fact
    -- about that kind of work, and changing it re-prices everything it does
    -- next against terms nobody quoted. Changing the regime is a retirement
    -- plus a new declaration, which leaves a record of both.
    IF NEW.pricing_mode IS DISTINCT FROM OLD.pricing_mode THEN
        RAISE EXCEPTION
            'pricing_mode is declared frozen (ADR-0007 §2): how a kind of '
            'work is sold is a fact about that kind of work, and changing it '
            're-prices everything it does next; retire this kind of work and '
            'declare a replacement instead. Got % to %',
            OLD.pricing_mode, NEW.pricing_mode
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_task_type_declared_transitions
BEFORE UPDATE ON ubb_task_type
FOR EACH ROW
WHEN (OLD.pricing_mode IS DISTINCT FROM NEW.pricing_mode)
EXECUTE FUNCTION ubb_task_type_declared_transitions();
"""

#: Contained work shares its parent's pricing regime.
#: Carried from work/0022_an_agreed_price_is_pinned_before_the_work_runs.
TASK_CONTAINMENT_SHARES_THE_PRICING_REGIME = """
CREATE FUNCTION ubb_task_containment_shares_the_pricing_regime() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    containing_regime text;
BEGIN
    SELECT pricing_mode INTO containing_regime
    FROM ubb_task WHERE id = NEW.parent_id;

    -- The parent is not on disk yet, so its regime is not a fact this rule
    -- can read. A foreign key that names no row is the deferred constraint's
    -- refusal at commit, and answering it here would attribute a referential
    -- fault to a pricing rule.
    IF NOT FOUND THEN
        RETURN NEW;
    END IF;

    -- Contained work is sold the way the work containing it is sold. A mixed
    -- tree produces a number nobody can explain: the rollup is unconditional,
    -- so metered revenue underneath an agreed price is added to a unit of work
    -- whose revenue that price was supposed to replace.
    IF containing_regime IS DISTINCT FROM NEW.pricing_mode THEN
        RAISE EXCEPTION
            'pricing_mode must match the unit of work containing this one: '
            'the containing unit is sold %, this one declares % — a mixed '
            'tree produces a number nobody can explain',
            containing_regime, NEW.pricing_mode
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_task_containment_shares_the_pricing_regime
BEFORE INSERT ON ubb_task
FOR EACH ROW
WHEN (NEW.parent_id IS NOT NULL)
EXECUTE FUNCTION ubb_task_containment_shares_the_pricing_regime();
"""

#: A unit of work is born once and ends once; UBB's stop facts are its own.
#: Carried from work/0029_a_units_stop_and_its_start_are_ubbs_own_record (its body is work/0028's refusals followed by 0029's, inlined).
TASK_DECLARED_TRANSITIONS = """
CREATE FUNCTION ubb_task_declared_transitions() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.parent_id IS DISTINCT FROM OLD.parent_id THEN
        RAISE EXCEPTION
            'parent_id is declared frozen (ADR-0007 §2): a unit of work is '
            'never re-parented, because everything it spent already rolled up '
            'into the work containing it. Got % to %',
            OLD.parent_id, NEW.parent_id
            USING ERRCODE = '23000';
    END IF;

    IF NEW.task_type IS DISTINCT FROM OLD.task_type THEN
        RAISE EXCEPTION
            'task_type is declared frozen (ADR-0007 §2): the kind of work a '
            'unit is decides what every event already settled on it means. '
            'Got % to %',
            OLD.task_type, NEW.task_type
            USING ERRCODE = '23000';
    END IF;

    IF NEW.status IS DISTINCT FROM OLD.status
            AND OLD.status <> 'active' THEN
        RAISE EXCEPTION
            'status is declared resolve_once (ADR-0007 §2): a unit of work '
            'leaves `active` once, for one terminal state, and '
            'that state never moves. Got % to %',
            OLD.status, NEW.status
            USING ERRCODE = '23000';
    END IF;

    -- The caller's explanation is written by the write that ENDS the work,
    -- from nothing, and by no other.
    IF NEW.outcome_reason IS DISTINCT FROM OLD.outcome_reason
            AND NOT (OLD.outcome_reason = ''
                     AND OLD.status = 'active'
                     AND NEW.status <> 'active') THEN
        RAISE EXCEPTION
            'outcome_reason is declared set_once (ADR-0007 §2): the caller''s '
            'reason is written by the write that ends the work and never '
            'again. Got % to % (status % to %)',
            OLD.outcome_reason, NEW.outcome_reason, OLD.status, NEW.status
            USING ERRCODE = '23000';
    END IF;

    IF NEW.reason_detail IS DISTINCT FROM OLD.reason_detail
            AND NOT (OLD.reason_detail = ''
                     AND OLD.status = 'active'
                     AND NEW.status <> 'active') THEN
        RAISE EXCEPTION
            'reason_detail is declared set_once (ADR-0007 §2): the sentence '
            'beside the caller''s reason is written by the write that ends the '
            'work and never again. Got % to % (status % to %)',
            OLD.reason_detail, NEW.reason_detail, OLD.status, NEW.status
            USING ERRCODE = '23000';
    END IF;

    IF OLD.reason_code IS NOT NULL AND NEW.reason_code IS DISTINCT FROM OLD.reason_code THEN
        RAISE EXCEPTION
            'reason_code is declared set_once (ADR-0007 §2): a stop UBB recorded is never rewritten. Got % to %',
            OLD.reason_code, NEW.reason_code
            USING ERRCODE = '23000';
    END IF;

    IF OLD.trigger_source IS NOT NULL AND NEW.trigger_source IS DISTINCT FROM OLD.trigger_source THEN
        RAISE EXCEPTION
            'trigger_source is declared set_once (ADR-0007 §2): a stop UBB recorded is never rewritten. Got % to %',
            OLD.trigger_source, NEW.trigger_source
            USING ERRCODE = '23000';
    END IF;

    IF OLD.control_family IS NOT NULL AND NEW.control_family IS DISTINCT FROM OLD.control_family THEN
        RAISE EXCEPTION
            'control_family is declared set_once (ADR-0007 §2): a stop UBB recorded is never rewritten. Got % to %',
            OLD.control_family, NEW.control_family
            USING ERRCODE = '23000';
    END IF;

    IF OLD.control_id IS NOT NULL AND NEW.control_id IS DISTINCT FROM OLD.control_id THEN
        RAISE EXCEPTION
            'control_id is declared set_once (ADR-0007 §2): a stop UBB recorded is never rewritten. Got % to %',
            OLD.control_id, NEW.control_id
            USING ERRCODE = '23000';
    END IF;

    IF NEW.start_absolute_deadline_seconds IS DISTINCT FROM OLD.start_absolute_deadline_seconds THEN
        RAISE EXCEPTION
            'start_absolute_deadline_seconds is declared frozen (ADR-0007 §2): it is the expiry policy the start published, and a replay repeats it. Got % to %',
            OLD.start_absolute_deadline_seconds, NEW.start_absolute_deadline_seconds
            USING ERRCODE = '23000';
    END IF;

    IF NEW.start_silence_window_seconds IS DISTINCT FROM OLD.start_silence_window_seconds THEN
        RAISE EXCEPTION
            'start_silence_window_seconds is declared frozen (ADR-0007 §2): it is the expiry policy the start published, and a replay repeats it. Got % to %',
            OLD.start_silence_window_seconds, NEW.start_silence_window_seconds
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_task_declared_transitions
BEFORE UPDATE ON ubb_task
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status OR OLD.parent_id IS DISTINCT FROM NEW.parent_id OR OLD.task_type IS DISTINCT FROM NEW.task_type OR OLD.outcome_reason IS DISTINCT FROM NEW.outcome_reason OR OLD.reason_detail IS DISTINCT FROM NEW.reason_detail OR OLD.reason_code IS DISTINCT FROM NEW.reason_code OR OLD.trigger_source IS DISTINCT FROM NEW.trigger_source OR OLD.control_family IS DISTINCT FROM NEW.control_family OR OLD.control_id IS DISTINCT FROM NEW.control_id OR OLD.start_absolute_deadline_seconds IS DISTINCT FROM NEW.start_absolute_deadline_seconds OR OLD.start_silence_window_seconds IS DISTINCT FROM NEW.start_silence_window_seconds)
EXECUTE FUNCTION ubb_task_declared_transitions();
"""


def _uninstall(trigger, table, function):
    return f"DROP TRIGGER {trigger} ON {table};\nDROP FUNCTION {function}();"


class Migration(migrations.Migration):

    dependencies = [
        ("work", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            [TASK_TYPE_DECLARED_TRANSITIONS],
            [_uninstall("trg_task_type_declared_transitions", "ubb_task_type", "ubb_task_type_declared_transitions")],
        ),
        migrations.RunSQL(
            [TASK_CONTAINMENT_SHARES_THE_PRICING_REGIME],
            [_uninstall("trg_task_containment_shares_the_pricing_regime", "ubb_task", "ubb_task_containment_shares_the_pricing_regime")],
        ),
        migrations.RunSQL(
            [TASK_DECLARED_TRANSITIONS],
            [_uninstall("trg_task_declared_transitions", "ubb_task", "ubb_task_declared_transitions")],
        ),
    ]
