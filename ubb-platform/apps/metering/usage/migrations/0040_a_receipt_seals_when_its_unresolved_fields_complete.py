"""A receipt seals when its last unresolved field completes (#353).

#349 made the Pricing Receipt the record that explains an amount and #350 made
it outlive the measurements it explains. Both are statements about what a
receipt CONTAINS. Neither says anything about what may happen to one after it is
written — and a record that can be edited is not an authority, it is a cache of
the configuration with extra steps. That is the failure the pricing-versions
decision exists to prevent: **a historical price must not be editable into a
different historical price.**

**TWO PROPERTIES, AND THE SECOND IS WHAT MAKES REMEDIATION POSSIBLE WHILE
MAKING REVISION IMPOSSIBLE.**

* Once complete, a receipt cannot change at all.
* A field recorded as unresolved completes **exactly once** — the only write a
  recovery run is ever permitted, and a second one is a revision wearing a
  recovery's clothes.

Sealing is the join of the two: the record becomes immutable when its last
unresolved field completes, and before that it is immutable except for the
completion of a field that is still unresolved.

**⚠ THE RECEIPT IS A COLUMN ON THIS TABLE, NOT A TABLE OF ITS OWN.** It is
`Posting.RECEIPT_COLUMN`, one `jsonb` record per posting. So this rule is a
THIRD rule on `ubb_posting`, not a rule on a second table — and everything the
sibling rules had to establish about telling one rule from another on one table
applies here with one more rule to be told apart. What makes this rule provable
in isolation is not that it lives elsewhere: it is that it names a **disjoint
column**, refuses with **its own column in the message**, and drops without
disturbing either neighbour. A single trigger carrying all three would make each
one's green claimable by the other two.

**THE MECHANISM IS `0037`'s AND `0039`'s, EXTENDED TO A THIRD RULE.** The
reasons are unchanged and they are the reasons a transition needs a trigger at
all: a `CHECK` is evaluated against one row and cannot see `OLD`, so it can say
whether a receipt is well-formed and can never say whether the one it replaced
was; and a Postgres `RULE` rewrites the statement rather than judging it. What
is refused, again, is a second KIND of mechanism over a sibling column on one
table, which is how two rules come to disagree about one write.

**WHY THIS IS NOT `0039` WITH AN EXTRA BRANCH.** The price pair's rule and this
one govern disjoint columns, their `WHEN` clauses name only their own, and their
permitted moves are different statements about different things — `unknown` to
`known` on three scalar columns there, the completion of one section of a
`jsonb` record here. Merged, every write touching either would evaluate both
bodies, and a single green would be claimed by both rules at once.

**THE TWO RULES DO FIRE TOGETHER, ON PURPOSE, AND EACH ADMITS THE SAME
STATEMENT.** A recovery that resolves a price writes `billed_cost_micros`,
`pricing_status` **and** the receipt in one `UPDATE`: the pair's rule reads it
as `unknown` → `known` and this one reads it as the completion of the receipt's
`pricing` section. Both admit it and neither knows about the other, which is the
property a merged rule would have removed. It is asserted in
`test_a_receipt_seals_once_it_is_complete.py`, not assumed here.

**WHAT COUNTS AS AN UNRESOLVED FIELD, TAKEN FROM THE RECORD'S OWN RULE.**
`apps/metering/pricing/receipts.py` already holds each section's amount, status
and method to agreeing: *an amount is present exactly when the status says the
resolution is settled, and the method is present on exactly the same
condition.* So the fields that are null exactly while a section is unresolved
are that section's `method` and its amount under `totals` — and its `status` is
the discriminator that moves with them. This rule is that sentence one level up:
**a section whose status is not settled is completable, once, as a whole.**

Its `detail` moves with it, and that is a decision rather than an oversight. A
completion is the statement that turns *here is what a recovery will need* into
*here is how the amount was arrived at*, and those are different content in the
same slot: an unresolved costing section carries the quantities that went
uncosted, and a completed one carries the components that explain the amount,
which the receipt boundary requires to carry their terms by value. A rule
admitting only additions there would seal a completed section still advertising
the quantities nobody had costed. What is refused is that section moving **at
all** once it is settled, and every other part of the record moving **ever**.

**`provenance` MAY GAIN A KEY, AND ONLY ON A STATEMENT THAT COMPLETES
SOMETHING.** The receipt's shape says provenance carries the ids of the matched
rule, the publish, the cost rates *and where applicable the run that completed
it* — so a completion has to be able to record which run made it. Containment
(`@>`) is what is asked, so nothing already recorded can change or vanish, only
arrive. And it is asked only where a section completed: without that condition a
sealed receipt could accumulate cross-references forever, which is the first
property above with a hole in it.

**WHAT IS FROZEN WHOLE, AND WHY THAT IS THE RIGHT ANSWER RATHER THAN A GAP.**
A record with no section to complete has nothing this rule can admit, so it
cannot be written at all. That covers the empty default, which explains nothing
and so has nothing to complete; and it covers **receipts written under the older
shape**, which the receipt module's own ruling already says are *read, never
rewritten* — the cutover squash is what removes them, not a rule here quietly
rewriting them into today's shape.

**The tokens below are literals, and the model's are not.** `known` is frozen
into the function body for the reason `0036`, `0037` and `0039` all give: a
migration records the schema as it was on the day it ran, and importing living
constants into a frozen file makes replay depend on today's registry. What keeps
the copy honest is a test rather than this file —
`test_a_receipt_seals_once_it_is_complete.py::TheRuleIsHeldByAThirdTriggerOnThis
TableTest::test_the_rule_names_the_settled_statuses_the_registry_declares` reads
the installed function's source out of `pg_proc` and compares it against
`core.vocabulary`, and the section and totals keys against the receipt module's
own, so a rename in either turns red here rather than leaving a rule that
quietly matches nothing.

**Why there is no vendor guard**, when the neighbouring raw-SQL migrations all
have one: `0011`, `0017` and `0022` guard on `connection.vendor` because a GIN
index is an optimisation and a backend without one still holds the data
correctly. This is not an optimisation — it is the enforcement half of a
declaration the model now makes, and a guard would encode a fallback in which
the promise is made and nothing keeps it.

**The refusal is raised as SQLSTATE 23000**, `integrity_constraint_violation`,
the class Django maps to `IntegrityError` — the same exception the two sibling
rules and the table's `CHECK`s raise, because a caller has no business caring
which mechanism held the line. The *message* is what distinguishes them, and
every one below names this rule's own column.

**The reverse is real and it is total.** Dropping this trigger and its function
returns the table to what `0039` left, which is a table whose receipts are
well-formed and whose receipts are editable. Nothing has to be unpicked because
nothing was written: this migration adds no column and moves no row.
"""

from django.db import migrations

TRIGGER = "trg_posting_receipt_sealing"
FUNCTION = "ubb_posting_receipt_sealing"

RECEIPT = "pricing_provenance"

INSTALL = f"""
CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    -- The two sections of the record, each with the key its amount sits under
    -- in `totals`. One array rather than two copies of one branch: the rule is
    -- the same rule on both sides of the margin, and the day somebody repairs
    -- it they repair it for the price side as well as the cost side.
    sections   text[][] := ARRAY[['costing', 'provider_cost_micros'],
                                 ['pricing', 'billed_cost_micros']];
    was        jsonb := OLD.{RECEIPT};
    becomes    jsonb := NEW.{RECEIPT};
    -- `becomes`, with every slot a completion is allowed to move put back to
    -- what it was. If the statement moved nothing else, this is `was` exactly.
    -- Anything else the statement touched survives into the comparison at the
    -- foot of this function, which is what makes the rule a statement about the
    -- WHOLE record rather than about the fields somebody thought to enumerate.
    rebuilt    jsonb;
    completed  boolean := false;
    section    text;
    amount_key text;
    old_side   jsonb;
    new_side   jsonb;
    old_amount jsonb;
    new_amount jsonb;
    at_section int;
BEGIN
    IF becomes IS NOT DISTINCT FROM was THEN
        RETURN NEW;
    END IF;

    rebuilt := becomes;

    FOR at_section IN 1..array_length(sections, 1) LOOP
        section := sections[at_section][1];
        amount_key := sections[at_section][2];
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
                '{RECEIPT} is declared resolve_once (ADR-0007 §2): this record '
                'has no % section to complete, so nothing in it may be '
                'written; a receipt in an older shape is read, never rewritten',
                section
                USING ERRCODE = '23000';
        END IF;

        IF old_side ->> 'status' = 'known' THEN
            RAISE EXCEPTION
                '{RECEIPT} is declared resolve_once (ADR-0007 §2): the % '
                'section is already settled and a settled section is sealed; '
                'changing an amount that was asserted is a correction, which '
                'belongs in a separate record beside the original',
                section
                USING ERRCODE = '23000';
        END IF;

        IF new_side ->> 'status' IS DISTINCT FROM 'known'
           OR COALESCE(jsonb_typeof(new_side -> 'method'), 'null') = 'null'
           OR COALESCE(jsonb_typeof(new_amount), 'null') = 'null' THEN
            RAISE EXCEPTION
                '{RECEIPT} is declared resolve_once (ADR-0007 §2): the only '
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
            '{RECEIPT} is declared resolve_once (ADR-0007 §2): this statement '
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
            '{RECEIPT} is declared resolve_once (ADR-0007 §2): provenance '
            'carries what has already been recorded; a completion may add a '
            'cross-reference to it and may not change or drop one'
            USING ERRCODE = '23000';
    END IF;
    rebuilt := jsonb_set(rebuilt, ARRAY['provenance'], was -> 'provenance');

    IF rebuilt IS DISTINCT FROM was THEN
        RAISE EXCEPTION
            '{RECEIPT} is declared resolve_once (ADR-0007 §2): a completion '
            'moves the section it completes and nothing else; this statement '
            'also changed a field that was never unresolved'
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER {TRIGGER}
BEFORE UPDATE ON ubb_posting
FOR EACH ROW
WHEN (OLD.{RECEIPT} IS DISTINCT FROM NEW.{RECEIPT})
EXECUTE FUNCTION {FUNCTION}();
"""

UNINSTALL = f"""
DROP TRIGGER {TRIGGER} ON ubb_posting;
DROP FUNCTION {FUNCTION}();
"""


def install(apps, schema_editor):
    schema_editor.execute(INSTALL, params=None)


def uninstall(apps, schema_editor):
    schema_editor.execute(UNINSTALL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ("usage", "0039_a_price_resolves_once_and_the_table_holds_it"),
    ]

    operations = [
        migrations.RunPython(install, uninstall),
    ]
