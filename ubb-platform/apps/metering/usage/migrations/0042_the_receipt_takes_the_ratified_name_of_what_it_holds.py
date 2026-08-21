"""The receipt's column takes the ratified name of what it holds (#370).

**A RENAME, AND ONLY A RENAME.** The column keeps its type, its default, its
contents and its meaning. What changes is that it stops carrying a retired
spelling of the concept it holds. The record had THREE names — this column's,
an endpoint docstring calling it the receipt, and `apps/metering/CONTEXT.md`
calling it the audit trail, which already names the governance ledger — and the
registry ratified one of them. `pricing_receipt_subject_type` is the concept;
the other two are its `retired_aliases`; and the word `provenance` survives as
the name of a SECTION inside the record and nowhere else.

**ADR-0007 §1 GOVERNS THE SHAPE: `RenameField`, never `AddField` plus
`RemoveField`.** The difference is the rows. A rename is one
`ALTER TABLE ... RENAME COLUMN`, which carries every receipt across; an
add-plus-remove produces a correctly-named column holding an empty record, and
every test that asks only whether the new name exists passes over the loss. The
receipt is the authoritative record of what a tenant was charged, so what would
be lost is not recoverable from anywhere — re-deriving it from today's
configuration is the exact failure #148 §3 exists to prevent.

⚠ **HAND-WRITTEN, for the reason `0016`, `0026`, `0027` and `0034` all give.**
`makemigrations` only asks *"did you rename this?"* on a TTY, so a
non-interactive run writes the add-plus-remove pair silently. Nothing here was
generated.

**⚠ THERE IS NO DATA MIGRATION HERE, AND THAT IS A DECISION RATHER THAN AN
OMISSION.** The receipts on this column exist in two SHAPES — the legacy
unversioned one and the sectioned one — and #148 §4.6 governs both: *old
receipts are read, never rewritten.* A receipt records what the engine did on a
day, and back-dating one into a shape that did not exist then makes it a worse
record rather than a better one. `receipts.py` knows the SET of shapes it can
read and refuses anything outside it, and what eventually removes the older
shape is #155 §11's cutover squash — not this migration and no migration in
this slice. The read path is pinned at
`api/v1/tests/test_metering_endpoints.py`, which writes a receipt in the older
shape and reads it back through the endpoint unchanged.

**⚠ WHAT A COLUMN RENAME DOES NOT CARRY: A `plpgsql` FUNCTION BODY.**
`0040` installs `ubb_posting_receipt_sealing`, whose body reads `OLD.<column>`
and `NEW.<column>` and names the column in all seven of its refusal messages.
Postgres stores that body as TEXT in `pg_proc.prosrc`, so an
`ALTER TABLE ... RENAME COLUMN` leaves it spelling a column that no longer
exists: the rule stays installed, `pg_trigger` still lists it, and the first
`UPDATE` that fires it fails at runtime. A `CHECK` constraint would have
followed the rename; a trigger function does not. So the rule is taken off the
table and put back, on either side of the rename, in this migration's own
transaction.

**⚠ THREE OPERATIONS BECAUSE A MIGRATION IS REVERSED IN REVERSE ORDER, AND TWO
WOULD BE CORRECT IN ONE DIRECTION ONLY.** Django runs `[X, Y]` forwards as
`X, Y` and backwards as `Y⁻¹, X⁻¹`. A rename plus a redefinition is therefore
`RENAME; DEFINE(new)` forwards and `DEFINE(old); RENAME back` backwards — and
that second sequence creates a trigger naming a column that will not exist for
another statement, so it fails. Bracketing the rename instead is symmetric:
drop, rename, define. Reversed it is drop, rename back, define, which is the
same three moves in the same order.

The DDL below is `0040`'s, spliced in unchanged apart from the column name, and
it is rendered from ONE template in both directions — so the reverse cannot
drift from the forward, which is the failure a hand-copied second body has.

**THE REVERSE IS TOTAL.** The column goes back to its retired spelling and the
rule goes back to naming it. Nothing was written, so nothing has to be unpicked.

The migrations tree is a declared sweep exclusion
(`gates/forbidden-term-sweep.yaml`), so the retired word legitimately survives
in this file — a rename migration that could not name what it retires would not
be reviewable. That exclusion covers every migration directory WHOLESALE, so
its count moves for this file whatever the file spells.
"""

from django.db import migrations

#: `0040`'s trigger and its function, addressed by name because a name is the
#: identity Postgres keeps across a column rename.
TRIGGER = "trg_posting_receipt_sealing"
FUNCTION = "ubb_posting_receipt_sealing"

#: The two spellings, in the direction they move.
RETIRED = "pricing_provenance"
RATIFIED = "pricing_receipt"

#: `0040`'s DDL with the column name left as a parameter. ONE copy, rendered
#: twice: forward under the ratified name and backward under the retired one, so
#: a body that drifted would have to drift in both directions at once.
INSTALL = """
CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $$
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
    was        jsonb := OLD.{receipt};
    becomes    jsonb := NEW.{receipt};
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
                '{receipt} is declared resolve_once (ADR-0007 §2): this record '
                'has no % section to complete, so nothing in it may be '
                'written; a receipt in an older shape is read, never rewritten',
                section
                USING ERRCODE = '23000';
        END IF;

        IF old_side ->> 'status' = 'known' THEN
            RAISE EXCEPTION
                '{receipt} is declared resolve_once (ADR-0007 §2): the % '
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
                '{receipt} is declared resolve_once (ADR-0007 §2): the % '
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
                '{receipt} is declared resolve_once (ADR-0007 §2): the only '
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
            '{receipt} is declared resolve_once (ADR-0007 §2): this statement '
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
            '{receipt} is declared resolve_once (ADR-0007 §2): provenance '
            'carries what has already been recorded; a completion may add a '
            'cross-reference to it and may not change or drop one'
            USING ERRCODE = '23000';
    END IF;
    rebuilt := jsonb_set(rebuilt, ARRAY['provenance'], was -> 'provenance');

    IF rebuilt IS DISTINCT FROM was THEN
        RAISE EXCEPTION
            '{receipt} is declared resolve_once (ADR-0007 §2): a completion '
            'moves the section it completes and nothing else; this statement '
            'also changed a field that was never unresolved'
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER {trigger}
BEFORE UPDATE ON ubb_posting
FOR EACH ROW
WHEN (OLD.{receipt} IS DISTINCT FROM NEW.{receipt})
EXECUTE FUNCTION {function}();"""

UNINSTALL = """
DROP TRIGGER {trigger} ON ubb_posting;
DROP FUNCTION {function}();"""


def _install(column):
    def install(apps, schema_editor):
        schema_editor.execute(
            INSTALL.format(receipt=column, trigger=TRIGGER, function=FUNCTION),
            params=None)
    return install


def _uninstall(apps, schema_editor):
    schema_editor.execute(
        UNINSTALL.format(trigger=TRIGGER, function=FUNCTION), params=None)


#: The rule as it stands AFTER this migration, which is the one a test that
#: exercises the reverse has to drive: `install` is the live definition and
#: `_uninstall` is what takes it off.
install = _install(RATIFIED)


class Migration(migrations.Migration):

    dependencies = [
        ("usage", "0041_a_measurement_is_pruned_only_when_it_may_be"),
    ]

    operations = [
        migrations.RunPython(_uninstall, _install(RETIRED)),
        migrations.RenameField(
            model_name="posting",
            old_name=RETIRED,
            new_name=RATIFIED,
        ),
        migrations.RunPython(install, _uninstall),
    ]
