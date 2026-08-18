"""The posting table starts refusing every price move but the resolution (#352).

#351 made `billed_cost_micros` nullable so that *not resolved* became sayable,
and put the four legal combinations of amount, status and reason into a `CHECK`.
A `CHECK` is evaluated against **one row**: it can say whether the row in front
of it is legal, and it cannot say whether the row it replaced was. That is
exactly the difference ADR-0007 §2 draws — *"resolution completes previously
unknown information; correction changes a value that was already asserted"* — so
until this migration, completing a blank price and changing an answer were
indistinguishable at the database.

**THE MECHANISM IS `0037`'s, EXTENDED TO A SECOND RULE — NOT A SECOND MECHANISM.**
The choice was between a trigger, a `CHECK` and a Postgres `RULE`, and it is the
same choice `0037` made for the same reasons: a `CHECK` cannot see `OLD` at all,
and a `RULE` rewrites the statement rather than judging it. What is new here is
the question `0037` did not face — whether this pair's rule belongs *inside*
that trigger's function or beside it in one of its own. It is beside it, and
the argument is that the two rules govern **disjoint columns**:

* each `WHEN` clause names only its own three columns, so a supplier settlement
  never enters the price function and a price resolution never enters the cost
  one. Merged, every write touching either pair would evaluate both bodies.
* the two pairs' permitted moves are different statements — `unresolved` →
  `known` on one side, `unknown` → `known` on the other — and a single function
  carrying both would need each branch to establish which pair it was looking
  at before it could say anything.
* dropping one rule leaves the other standing, which is what makes the reverse
  below a real reverse and each measurable on its own.

What is *refused* is a second **mechanism**: a `CHECK` or a `RULE` holding the
price pair while a trigger holds the cost pair. Two mechanisms enforcing sibling
pairs on one table is how the two rules end up disagreeing about the same write.

**⚠ AND A SECOND TRIGGER MEANS EVERY "EXACTLY ONE TRIGGER" ASSERTION ON THIS
TABLE IS NOW FALSE.** `pg_trigger` promises no order, so anything indexing the
first row it returns was reading whichever one Postgres happened to hand back.
Both this rule's tests and `0037`'s address their trigger **by name**, and the
table's rules are pinned as an exact set rather than a count.

**The one permitted move is `unknown` → `known`, and only that.** The other
three statuses are terminal by construction:

* `waived` is a decision somebody made not to pursue a charge. The spec's ruling
  12c settles that it is **never** a resolution candidate and that run membership
  is *"the status itself, not a separate flag"* — so the table is what keeps
  waived postings outside a run, rather than a selector everyone must remember.
* `not_applicable` says no customer revenue arises at this level at all.
* `known` is resolved; replacing it is a correction, and ADR-0007 §2 requires a
  correction to be *"a separate record beside the original"*.

`not_applicable_reason` moves with the pair and, unlike the cost side's reason,
is never cleared by anything: the status it belongs to is terminal on both
sides, so the only statement that may touch it is one that does not.

**The cost was measured rather than assumed**, because ADR-0007's Consequences
require it of this decision specifically and this is the hottest write path in
the system. `scripts/measure_posting_transition_cost.py` measures **both** rules
— it asks for each trigger by name, and it times a price resolution beside the
supplier settlement — and the numbers are in the acceptance record for #352.
The shape is `0037`'s: `BEFORE UPDATE` only, so **inserts pay nothing at all**,
and the `WHEN` clause means an update leaving all three columns alone never
enters the function body either.

**Why there is no vendor guard**, when the neighbouring raw-SQL migrations all
have one: `0011`, `0017` and `0022` guard on `connection.vendor` because a GIN
index is an optimisation, and a backend without one still holds the data
correctly. This is not an optimisation — it is the enforcement half of a
declaration the model now makes, and a guard would encode a fallback in which
the promise is made and nothing keeps it. That is the precise state
`apps/platform/tests/test_transition_class_declarations.py` exists to refuse.

**The tokens below are literals, and the model's are not.** `unknown` and
`known` are frozen into the function body for the reason `0036` gives at length:
a migration records the schema as it was on the day it ran, and importing living
constants into a frozen file makes replay depend on today's registry. What keeps
the copy honest is not this file but a test —
`test_a_price_resolves_once.py::TheRuleIsHeldByASecondTriggerOnThisTableTest::
test_the_rule_names_the_status_values_the_registry_declares` reads the installed
function's source out of `pg_proc` and compares it against `core.vocabulary`, so
a rename in `domain-vocabulary/` turns red here rather than leaving a rule that
quietly matches nothing. That module also RUNS the reverse below, both
directions, against a real refusal — and asserts the cost rule is still standing
at each end, so a reverse that took its neighbour down with it fails here.

**The refusal is raised as SQLSTATE 23000**, `integrity_constraint_violation`,
which is the class Django maps to `IntegrityError` — the same exception the
`CHECK` constraints beside it raise, because a caller has no business caring
which mechanism held the line. The *message* distinguishes them: this one names
the transition class it is enforcing, and a `CHECK` names its own constraint.

**The reverse is real and it is total.** Dropping this trigger and its function
returns the table to what `0038` left, which is a table whose price combinations
are still checked and whose price history is not. Nothing has to be unpicked
because nothing was written: this migration adds no column and moves no row.
"""

from django.db import migrations

TRIGGER = "trg_posting_price_transitions"
FUNCTION = "ubb_posting_price_transitions"

INSTALL = f"""
CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- billed_cost_micros and pricing_status are declared RESOLVE_ONCE AS A
    -- PAIR, and not_applicable_reason moves with them: the one permitted
    -- statement completes the amount and moves the status to known at once,
    -- from a posting whose price UBB could not resolve.
    --
    -- The four refusals this one condition carries, each named in
    -- test_a_price_resolves_once.py:
    --   OLD.pricing_status <> 'unknown'  -- waived and not_applicable are
    --                                       terminal; known is a correction
    --   OLD.billed_cost_micros IS NOT NULL  -- a resolved amount is not
    --                                          re-resolved
    --   NEW.pricing_status <> 'known'    -- unknown does not become waived or
    --                                       not_applicable by relabelling
    --   NEW.billed_cost_micros IS NULL   -- half a resolution is not one
    --   NEW.not_applicable_reason IS NOT NULL  -- a priced row never carries
    --                                             a reason it has no price
    IF NEW.billed_cost_micros IS DISTINCT FROM OLD.billed_cost_micros
       OR NEW.pricing_status IS DISTINCT FROM OLD.pricing_status
       OR NEW.not_applicable_reason IS DISTINCT FROM OLD.not_applicable_reason
    THEN
        IF OLD.pricing_status <> 'unknown'
           OR OLD.billed_cost_micros IS NOT NULL
           OR NEW.pricing_status <> 'known'
           OR NEW.billed_cost_micros IS NULL
           OR NEW.not_applicable_reason IS NOT NULL THEN
            RAISE EXCEPTION
                'billed_cost_micros and pricing_status are declared '
                'resolve_once (ADR-0007 §2): the only permitted move is '
                'unknown to known, completing the amount and moving the '
                'status in one statement; got % to %',
                OLD.pricing_status, NEW.pricing_status
                USING ERRCODE = '23000';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER {TRIGGER}
BEFORE UPDATE ON ubb_posting
FOR EACH ROW
WHEN (OLD.billed_cost_micros IS DISTINCT FROM NEW.billed_cost_micros
      OR OLD.pricing_status IS DISTINCT FROM NEW.pricing_status
      OR OLD.not_applicable_reason IS DISTINCT FROM NEW.not_applicable_reason)
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
        ("usage", "0038_a_price_ubb_cannot_resolve_stops_being_zero"),
    ]

    operations = [
        migrations.RunPython(install, uninstall),
    ]
