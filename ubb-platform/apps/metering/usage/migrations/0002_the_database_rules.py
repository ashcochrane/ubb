"""The usage app's database rules: the triggers no model declaration can hold.

Part of the fresh initial set the cutover regenerated (#190; ADR-0026). The schema
migration beside this one is generated from the final models; these rules are not
in Django's migration state, so they are carried here by hand. Each one is the
final installed definition the old migration chain left, carried exactly: the
function bodies are byte-for-byte the last installer's, and the refusal texts,
vocabulary literals and SQL aliases that tests compare are unchanged. Each
constant names the historical migration whose text it carries.

**The bodies' own comments are the old chain's words, verbatim**, because the
bodies are carried byte for byte: where one cites a migration by number ("as
0039 argues"), says no job sets `prunable_at` (true until the W5 prune), or
speaks of a receipt "in an older shape", it is the record of the day the rule
was written, and the cutover changed none of it.

Every rule refuses with SQLSTATE 23000. Each statement is passed to `RunSQL` as a
list item so it runs verbatim — a plain string would be split and comment-stripped
by `sqlparse`, which would change the stored function bodies.

DEPENDENCIES (§0.3 point 1): this migration depends on the schema leaf of every
app owning a table its SQL references, never on an assumed `0001`:
  trg_posting_declared_transitions: ubb_posting (usage)
  trg_posting_price_transitions: ubb_posting (usage)
  trg_posting_receipt_sealing: ubb_posting (usage)
  trg_posting_measurement_pruning: ubb_posting_measurement (usage), ubb_posting (usage), ubb_tenant (tenants)
  trg_posting_kind_frozen: ubb_posting (usage)
  trg_stop_acknowledgement_is_insert_only: ubb_stop_acknowledgement (usage), ubb_posting (usage), ubb_tenant (tenants)
  trg_posting_measurement_released_once: ubb_posting_measurement (usage)
"""
from django.db import migrations


#: A cost settles once.
#: Carried from usage/0037_a_cost_settles_once_and_the_table_holds_it.
POSTING_DECLARED_TRANSITIONS = """
CREATE FUNCTION ubb_posting_declared_transitions() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- claimed_provider_cost_micros is declared FROZEN: what the caller said is
    -- a record of what was said, so it takes no value after insert and changes
    -- none.
    IF NEW.claimed_provider_cost_micros
       IS DISTINCT FROM OLD.claimed_provider_cost_micros THEN
        RAISE EXCEPTION
            'claimed_provider_cost_micros is declared frozen (ADR-0007 §2): '
            'a claim is a record of what was said at the time'
            USING ERRCODE = '23000';
    END IF;

    -- provider_cost_micros and costing_status are declared RESOLVE_ONCE AS A
    -- PAIR, and unresolved_reason moves with them: the one permitted statement
    -- sets the amount, moves the status to known and clears the reason at once.
    IF NEW.provider_cost_micros IS DISTINCT FROM OLD.provider_cost_micros
       OR NEW.costing_status IS DISTINCT FROM OLD.costing_status
       OR NEW.unresolved_reason IS DISTINCT FROM OLD.unresolved_reason THEN
        IF OLD.costing_status <> 'unresolved'
           OR OLD.provider_cost_micros IS NOT NULL
           OR NEW.costing_status <> 'known'
           OR NEW.provider_cost_micros IS NULL
           OR NEW.unresolved_reason IS NOT NULL THEN
            RAISE EXCEPTION
                'provider_cost_micros and costing_status are declared '
                'resolve_once (ADR-0007 §2): the only permitted move is '
                'unresolved to known, settling the amount and clearing the '
                'reason in one statement; got % to %',
                OLD.costing_status, NEW.costing_status
                USING ERRCODE = '23000';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_posting_declared_transitions
BEFORE UPDATE ON ubb_posting
FOR EACH ROW
WHEN (OLD.provider_cost_micros IS DISTINCT FROM NEW.provider_cost_micros
      OR OLD.costing_status IS DISTINCT FROM NEW.costing_status
      OR OLD.unresolved_reason IS DISTINCT FROM NEW.unresolved_reason
      OR OLD.claimed_provider_cost_micros
         IS DISTINCT FROM NEW.claimed_provider_cost_micros)
EXECUTE FUNCTION ubb_posting_declared_transitions();
"""

#: A customer price resolves once, and only through its door.
#: Carried from two migrations: the function is
#: usage/0049_a_customer_price_becomes_known_only_through_its_door (the price
#: door, #557); the trigger statement is
#: usage/0046_the_price_status_carries_its_own_reason.
POSTING_PRICE_TRANSITIONS = """
CREATE FUNCTION ubb_posting_price_transitions() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- billed_cost_micros and pricing_status are declared RESOLVE_ONCE AS A
    -- PAIR, and not_applicable_reason and pricing_status_reason move with
    -- them: the one permitted statement completes the amount and moves the
    -- status to known at once, from a posting whose price UBB could not
    -- resolve, and leaves both reasons NULL.
    --
    -- SIX conditions, FIVE of which a test drives directly:
    --   OLD.pricing_status <> 'unknown'  -- waived and not_applicable are
    --                                       terminal; known is a correction
    --   NEW.pricing_status <> 'known'    -- unknown does not become waived or
    --                                       not_applicable by relabelling
    --   NEW.billed_cost_micros IS NULL   -- half a resolution is not one
    --   NEW.not_applicable_reason IS NOT NULL  -- a priced row never carries
    --                                             a reason saying it has none
    --   NEW.pricing_status_reason IS NOT NULL  -- nor one saying why it was
    --                                             unknown (#603)
    --
    -- The sixth, OLD.billed_cost_micros IS NOT NULL, is DEFENCE IN DEPTH, as
    -- 0039 argues: no committed `unknown` row can reach it past the CHECK.
    IF NEW.billed_cost_micros IS DISTINCT FROM OLD.billed_cost_micros
       OR NEW.pricing_status IS DISTINCT FROM OLD.pricing_status
       OR NEW.not_applicable_reason IS DISTINCT FROM OLD.not_applicable_reason
       OR NEW.pricing_status_reason IS DISTINCT FROM OLD.pricing_status_reason
    THEN
        IF OLD.pricing_status <> 'unknown'
           OR OLD.billed_cost_micros IS NOT NULL
           OR NEW.pricing_status <> 'known'
           OR NEW.billed_cost_micros IS NULL
           OR NEW.not_applicable_reason IS NOT NULL
           OR NEW.pricing_status_reason IS NOT NULL THEN
            RAISE EXCEPTION
                'billed_cost_micros and pricing_status are declared '
                'resolve_once (ADR-0007 §2): the only permitted move is '
                'unknown to known, completing the amount and moving the '
                'status in one statement; got % to %',
                OLD.pricing_status, NEW.pricing_status
                USING ERRCODE = '23000';
        END IF;
        -- AND THE PERMITTED MOVE IS THE DOOR'S ALONE (#557).
        IF current_setting('ubb.price_door', true)
           IS DISTINCT FROM 'resolve_customer_price' THEN
            RAISE EXCEPTION
                'billed_cost_micros and pricing_status are declared '
                'resolve_once, and a customer price becomes known only '
                'through its door, price_resolution.resolve_customer_price '
                '(#557): this statement resolved one without the mark that '
                'door sets'
                USING ERRCODE = '23000';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_posting_price_transitions
BEFORE UPDATE ON ubb_posting
FOR EACH ROW
WHEN (OLD.billed_cost_micros IS DISTINCT FROM NEW.billed_cost_micros
      OR OLD.pricing_status IS DISTINCT FROM NEW.pricing_status
      OR OLD.not_applicable_reason IS DISTINCT FROM NEW.not_applicable_reason
      OR OLD.pricing_status_reason IS DISTINCT FROM NEW.pricing_status_reason)
EXECUTE FUNCTION ubb_posting_price_transitions();
"""

#: A Pricing Receipt seals once it is complete.
#: Carried from usage/0042_the_receipt_takes_the_ratified_name_of_what_it_holds (its re-install on the renamed column).
POSTING_RECEIPT_SEALING = """
CREATE FUNCTION ubb_posting_receipt_sealing() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    -- The two sections of the record: its name, the key its amount sits under
    -- in `totals`, and THE ONE STATUS A COMPLETION MAY START FROM. One array
    -- rather than two copies of one branch: the rule is the same rule on both
    -- sides of the margin, and the day somebody repairs it they repair it for
    -- the price side as well as the cost side.
    --
    -- ⚠ THE THIRD COLUMN IS A WHITELIST AND MUST STAY ONE. Every unsettled
    -- status leaves a section's method and amount null — `unresolved` and
    -- `unknown`, which say UBB does not have the information, and `waived` and
    -- `not_applicable`, which say a decision was made — so "not settled" and
    -- "completable" are indistinguishable in the SHAPE and are different facts.
    -- Blacklisting the settled status instead would make a waived charge
    -- completable into a charged amount, on a statement that fires neither
    -- sibling rule, leaving the record and the column beside it saying
    -- different things. `core.amount_status_pairs` names exactly one
    -- `unresolved_status` per pair for the same reason, and `0037` and `0039`
    -- whitelist theirs.
    sections   text[][] := ARRAY[
                   ['costing', 'provider_cost_micros', 'unresolved'],
                   ['pricing', 'billed_cost_micros', 'unknown']];
    was        jsonb := OLD.pricing_receipt;
    becomes    jsonb := NEW.pricing_receipt;
    -- `becomes`, with every slot a completion is allowed to move put back to
    -- what it was. If the statement moved nothing else, this is `was` exactly.
    -- Anything else the statement touched survives into the comparison at the
    -- foot of this function, which is what makes the rule a statement about the
    -- WHOLE record rather than about the fields somebody thought to enumerate.
    rebuilt    jsonb;
    completed  boolean := false;
    section    text;
    amount_key text;
    completable text;
    old_side   jsonb;
    new_side   jsonb;
    old_amount jsonb;
    new_amount jsonb;
    at_section int;
BEGIN
    -- UNREACHABLE UNDER THE `WHEN` CLAUSE BELOW, and kept for the reason `0037`
    -- and `0039` keep their own re-tests of their `WHEN` conditions: the two are
    -- altered by different statements, and a body that depends on its trigger
    -- definition still saying what it says today is a body that stops holding
    -- silently. Written down as unreachable rather than left looking like the
    -- branch that catches a no-op write.
    IF becomes IS NOT DISTINCT FROM was THEN
        RETURN NEW;
    END IF;

    rebuilt := becomes;

    FOR at_section IN 1..array_length(sections, 1) LOOP
        section := sections[at_section][1];
        amount_key := sections[at_section][2];
        completable := sections[at_section][3];
        old_side := was -> section;
        new_side := becomes -> section;
        old_amount := was #> ARRAY['totals', amount_key];
        new_amount := becomes #> ARRAY['totals', amount_key];

        IF new_side IS NOT DISTINCT FROM old_side
           AND new_amount IS NOT DISTINCT FROM old_amount THEN
            CONTINUE;
        END IF;

        -- This section moved. Three questions, in the order that makes each
        -- refusal say the thing a reader needs to act on.
        IF jsonb_typeof(old_side) IS DISTINCT FROM 'object' THEN
            RAISE EXCEPTION
                'pricing_receipt is declared resolve_once (ADR-0007 §2): this record '
                'has no % section to complete, so nothing in it may be '
                'written; a receipt in an older shape is read, never rewritten',
                section
                USING ERRCODE = '23000';
        END IF;

        IF old_side ->> 'status' = 'known' THEN
            RAISE EXCEPTION
                'pricing_receipt is declared resolve_once (ADR-0007 §2): the % '
                'section is already settled and a settled section is sealed; '
                'changing an amount that was asserted is a correction, which '
                'belongs in a separate record beside the original',
                section
                USING ERRCODE = '23000';
        END IF;

        -- The terminal statuses, which are unsettled and are not completable.
        -- Separated from the branch above rather than folded into it because
        -- the two say different things to whoever hit them: one is a correction
        -- of a resolved amount, the other is a decision being undone.
        IF old_side ->> 'status' IS DISTINCT FROM completable THEN
            RAISE EXCEPTION
                'pricing_receipt is declared resolve_once (ADR-0007 §2): the % '
                'section says % and that is terminal — only a section recorded '
                'as % is completable, because a decision somebody made is not '
                'information UBB is missing',
                section, old_side ->> 'status', completable
                USING ERRCODE = '23000';
        END IF;

        IF new_side ->> 'status' IS DISTINCT FROM 'known'
           OR COALESCE(jsonb_typeof(new_side -> 'method'), 'null') = 'null'
           OR COALESCE(jsonb_typeof(new_amount), 'null') = 'null' THEN
            RAISE EXCEPTION
                'pricing_receipt is declared resolve_once (ADR-0007 §2): the only '
                'permitted move on the % section is its completion — the '
                'status to known, carrying a method and an amount in one '
                'statement; got status %',
                section, new_side ->> 'status'
                USING ERRCODE = '23000';
        END IF;

        completed := true;
        rebuilt := jsonb_set(rebuilt, ARRAY[section], old_side);
        rebuilt := jsonb_set(rebuilt, ARRAY['totals', amount_key],
                             COALESCE(old_amount, 'null'::jsonb));
    END LOOP;

    -- ⚠ THIS BRANCH COVERS THREE SITUATIONS AND THE MESSAGE MUST BE TRUE OF
    -- ALL THREE, not of the one that came to mind: a sealed receipt edited
    -- anywhere, an unresolved receipt edited somewhere that is not one of its
    -- sections, and a record with no sections at all. What they have in common
    -- is exactly what is said — the statement completes nothing — and a
    -- message asserting the third would be wrong for the first two, which are
    -- the commoner ones. A statement that moved a section but is not a
    -- completion never reaches here; it is refused above, where the section it
    -- moved can be named.
    IF NOT completed THEN
        RAISE EXCEPTION
            'pricing_receipt is declared resolve_once (ADR-0007 §2): this statement '
            'completes no unresolved field, and completing one is the only '
            'write a receipt admits — it is the authoritative record of what '
            'was charged, not a view of today''s configuration'
            USING ERRCODE = '23000';
    END IF;

    -- Cross-references may ARRIVE on the statement that completes a section —
    -- the run that completed it is one — and nothing already recorded may
    -- change or vanish. Containment is the whole of that claim, and it is asked
    -- here rather than above because a receipt nothing completed is sealed.
    -- Parenthesised because `->` and `@>` are the same precedence class and
    -- associate left, so the bare form parses as `((becomes -> 'provenance')
    -- @> was) -> 'provenance'` and fails to plan rather than answering wrongly.
    IF NOT COALESCE((becomes -> 'provenance') @> (was -> 'provenance'),
                    false) THEN
        RAISE EXCEPTION
            'pricing_receipt is declared resolve_once (ADR-0007 §2): provenance '
            'carries what has already been recorded; a completion may add a '
            'cross-reference to it and may not change or drop one'
            USING ERRCODE = '23000';
    END IF;
    rebuilt := jsonb_set(rebuilt, ARRAY['provenance'], was -> 'provenance');

    IF rebuilt IS DISTINCT FROM was THEN
        RAISE EXCEPTION
            'pricing_receipt is declared resolve_once (ADR-0007 §2): a completion '
            'moves the section it completes and nothing else; this statement '
            'also changed a field that was never unresolved'
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_posting_receipt_sealing
BEFORE UPDATE ON ubb_posting
FOR EACH ROW
WHEN (OLD.pricing_receipt IS DISTINCT FROM NEW.pricing_receipt)
EXECUTE FUNCTION ubb_posting_receipt_sealing();
"""

#: A measurement record is pruned only when it may be.
#: Carried from usage/0041_a_measurement_is_pruned_only_when_it_may_be.
POSTING_MEASUREMENT_PRUNING = """
CREATE FUNCTION ubb_posting_measurement_pruning() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    parent_is_sandbox   boolean;
    parent_costing_status text;
    parent_pricing_status text;
BEGIN
    -- The parent, read once. The foreign key makes exactly one row certain, and
    -- the collector deletes this child before its posting, so the row is on
    -- disk here even when the whole posting is on its way out.
    SELECT t.is_sandbox, p.costing_status, p.pricing_status
      INTO parent_is_sandbox, parent_costing_status, parent_pricing_status
      FROM ubb_posting p
      JOIN ubb_tenant t ON t.id = p.tenant_id
     WHERE p.id = OLD.posting_id;

    -- A sandbox carries neither obligation this rule protects: not the
    -- six-year retention promise and not the recovery a resolution run makes,
    -- both of which are statements about real customer money. Its reset button
    -- discards the tenant's postings wholesale, and discarding is not pruning.
    IF parent_is_sandbox THEN
        RETURN OLD;
    END IF;

    -- prunable_at names the moment a permission BEGINS, so an instant nobody
    -- has named is not one that has passed. Every row in the tree carries NULL
    -- here today, and no job, schedule or owner sets it.
    IF OLD.prunable_at IS NULL OR now() < OLD.prunable_at THEN
        RAISE EXCEPTION
            'ubb_posting_measurement is governed by a whole-record rule '
            '(ADR-0007 §2): a measurement may be pruned only at or after its '
            'prunable_at, and this one is %',
            COALESCE('due ' || OLD.prunable_at::text, 'not released by any clock')
            USING ERRCODE = '23000';
    END IF;

    -- NOT UNRESOLVED, rather than IS RESOLVED. Three of this posting's statuses
    -- carry a null amount because somebody decided something (waived,
    -- not_applicable on either side) and two because UBB is missing
    -- information; only the second kind is what a resolution run still needs
    -- these quantities for.
    IF parent_costing_status = 'unresolved'
       OR parent_pricing_status = 'unknown' THEN
        RAISE EXCEPTION
            'ubb_posting_measurement is governed by a whole-record rule '
            '(ADR-0007 §2): a measurement may be pruned only while its posting '
            'is not unresolved; costing_status is % and pricing_status is %',
            parent_costing_status, parent_pricing_status
            USING ERRCODE = '23000';
    END IF;

    RETURN OLD;
END;
$$;

CREATE TRIGGER trg_posting_measurement_pruning
BEFORE DELETE ON ubb_posting_measurement
FOR EACH ROW
EXECUTE FUNCTION ubb_posting_measurement_pruning();
"""

#: A posting's kind is settled at birth.
#: Carried from usage/0044_a_postings_kind_is_settled_at_birth.
POSTING_KIND_FROZEN = """
CREATE FUNCTION ubb_posting_kind_frozen() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- kind is declared FROZEN: none after insert. There is no permitted move,
    -- so this body has no legal branch to fall through to — a statement that
    -- reaches it has already changed the column, which the WHEN clause below
    -- established, and changing it is the whole of what is refused.
    --
    -- The two values are spelled in the message rather than tested, on
    -- purpose: what is refused is the MOVE and not the destination, so a rule
    -- that named a legal target would be a rule about which conversions are
    -- allowed, and none is.
    RAISE EXCEPTION
        'kind is declared frozen (ADR-0007 §2): a posting is born a '
        'metered_usage event or a task_charge projection and is never '
        'converted; got % to %',
        OLD.kind, NEW.kind
        USING ERRCODE = '23000';
END;
$$;

CREATE TRIGGER trg_posting_kind_frozen
BEFORE UPDATE ON ubb_posting
FOR EACH ROW
WHEN (OLD.kind IS DISTINCT FROM NEW.kind)
EXECUTE FUNCTION ubb_posting_kind_frozen();
"""

#: A recording keeps what its acknowledgement said.
#: Carried from usage/0045_a_recording_keeps_what_its_acknowledgement_said.
STOP_ACKNOWLEDGEMENT_IS_INSERT_ONLY = """
CREATE FUNCTION ubb_stop_acknowledgement_is_insert_only() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    on_a_sandbox boolean;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION
            'ubb_stop_acknowledgement is insert-only (#569, ADR-0019): what '
            'an acknowledgement said is kept as it was said, and a replay '
            'answers from it; refused an UPDATE of %', OLD.id
            USING ERRCODE = '23000';
    END IF;

    -- A sandbox's postings are discarded wholesale by its reset, and this
    -- record goes with its posting: a discard, not an edit.
    SELECT t.is_sandbox
      INTO on_a_sandbox
      FROM ubb_posting p
      JOIN ubb_tenant t ON t.id = p.tenant_id
     WHERE p.id = OLD.posting_id;
    IF on_a_sandbox THEN
        RETURN OLD;
    END IF;

    RAISE EXCEPTION
        'ubb_stop_acknowledgement is insert-only (#569, ADR-0019): what an '
        'acknowledgement said leaves only with a sandbox''s discarded '
        'postings; refused a DELETE of %', OLD.id
        USING ERRCODE = '23000';
END;
$$;

CREATE TRIGGER trg_stop_acknowledgement_is_insert_only
BEFORE UPDATE OR DELETE ON ubb_stop_acknowledgement
FOR EACH ROW
EXECUTE FUNCTION ubb_stop_acknowledgement_is_insert_only();
"""

#: A measurement record is released once, by the prune.
#: Carried from usage/0052_a_measurement_is_released_once_by_the_prune.
POSTING_MEASUREMENT_RELEASED_ONCE = """
CREATE FUNCTION ubb_posting_measurement_released_once() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.prunable_at IS NOT NULL THEN
        RAISE EXCEPTION
            'prunable_at is declared set_once (ADR-0007 §2): a measurement is '
            'released once, and its release is never moved or withdrawn. '
            'Got % to %',
            OLD.prunable_at, NEW.prunable_at
            USING ERRCODE = '23000';
    END IF;

    IF NEW.prunable_at > now() THEN
        RAISE EXCEPTION
            'prunable_at is declared set_once (ADR-0007 §2): it records when a '
            'measurement was released, so it cannot name a moment still to '
            'come. Got % at %',
            NEW.prunable_at, now()
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_posting_measurement_released_once
BEFORE UPDATE ON ubb_posting_measurement
FOR EACH ROW
WHEN (OLD.prunable_at IS DISTINCT FROM NEW.prunable_at)
EXECUTE FUNCTION ubb_posting_measurement_released_once();
"""


def _uninstall(trigger, table, function):
    return f"DROP TRIGGER {trigger} ON {table};\nDROP FUNCTION {function}();"


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0001_initial"),
        ("usage", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            [POSTING_DECLARED_TRANSITIONS],
            [_uninstall("trg_posting_declared_transitions", "ubb_posting", "ubb_posting_declared_transitions")],
        ),
        migrations.RunSQL(
            [POSTING_PRICE_TRANSITIONS],
            [_uninstall("trg_posting_price_transitions", "ubb_posting", "ubb_posting_price_transitions")],
        ),
        migrations.RunSQL(
            [POSTING_RECEIPT_SEALING],
            [_uninstall("trg_posting_receipt_sealing", "ubb_posting", "ubb_posting_receipt_sealing")],
        ),
        migrations.RunSQL(
            [POSTING_MEASUREMENT_PRUNING],
            [_uninstall("trg_posting_measurement_pruning", "ubb_posting_measurement", "ubb_posting_measurement_pruning")],
        ),
        migrations.RunSQL(
            [POSTING_KIND_FROZEN],
            [_uninstall("trg_posting_kind_frozen", "ubb_posting", "ubb_posting_kind_frozen")],
        ),
        migrations.RunSQL(
            [STOP_ACKNOWLEDGEMENT_IS_INSERT_ONLY],
            [_uninstall("trg_stop_acknowledgement_is_insert_only", "ubb_stop_acknowledgement", "ubb_stop_acknowledgement_is_insert_only")],
        ),
        migrations.RunSQL(
            [POSTING_MEASUREMENT_RELEASED_ONCE],
            [_uninstall("trg_posting_measurement_released_once", "ubb_posting_measurement", "ubb_posting_measurement_released_once")],
        ),
    ]
