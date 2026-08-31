"""Declared transition classes — what a column is allowed to become.

ADR-0007 §2 rules that no record claims to be "immutable" as a whole: **every
column is declared into exactly one class, and the database enforces the
permitted transition** regardless of which door the write came through. This
module is the vocabulary that declaration is written in — a model states its
classes in a ``transition_classes`` mapping beside its fields, so that the
question "what is allowed to happen to this?" is answered at model-definition
time. ADR-0007's Consequences names that as both the cost and the point.

**Declaring is not enforcing, and nothing in this module enforces anything.**
Database enforcement is gate G19, and slice 3 **installed** it: the trigger in
``apps/metering/usage/migrations/0037_a_cost_settles_once_and_the_table_holds_it.py``
holds the first columns declared here across ``save()``, ``QuerySet.update()``
and raw SQL alike, and
``apps/platform/tests/test_transition_class_declarations.py`` walks
every declaration in the tree and fails on any column the database does not
actually defend. Slice 4 **extended** that gate rather than re-owning it: the
posting's customer price pair is held by a second trigger, in
``…/migrations/0039_a_price_resolves_once_and_the_table_holds_it.py``, over
disjoint columns and in the same mechanism. Nothing *here* installs a trigger, a
rule or a ``CHECK`` — this module is the vocabulary, and the gates that hold a
column to what it says live with the table.

**Slice 5 (#414) is the first declarer outside a product**, and it extends the
gate the same way rather than re-owning it: ``TaskType.pricing_mode`` — how a
kind of work is sold — is ``FROZEN``, held by a third trigger in
``apps/platform/work/migrations/0021_a_kind_of_work_declares_how_it_is_sold.py``
over its own table. That the first three declarers were all in ``apps/metering``
was an accident of which slices came first, not a property of this vocabulary:
the kernel holds economic facts too.

**And #416 (``pricing.Charge``) is the largest declaration in the tree by some
way**, which is a difference of scale rather than of kind and is worth saying
because of what scale does to the assertions. What one delivered piece of work
sold at one agreed price is owed for declares **TWENTY** columns ``FROZEN``,
held by its own trigger in
``apps/metering/pricing/migrations/0031_a_delivered_piece_of_work_is_charged_once.py``.
Every other declarer is between one column and about eight, and their defended
columns are split across several rules over disjoint sets — so *something
refused this* narrowed to nearly one thing. Twenty columns under ONE rule
answering with one class word narrows to nothing at all, so that rule names the
COLUMNS THAT MOVED and every assertion about it names one too.

⚠ **The paragraphs above narrate the slices, not the tree, and neither counts
the rules.** "the first columns", "a second trigger", "a third trigger" are this
module's account of the declarations it was written to explain; six models in
the tree declare something today and more than three triggers hold them, so a
reader wanting the set should walk ``transition_classes`` rather than count the
ordinals here.

⚠ The Charge's three pointers are declared as their COLUMNS (``tenant_id``,
``task_id``, ``compensates_id``) rather than as their fields, because the walk
below searches a trigger body and a trigger says ``NEW.task_id`` — declaring the
field name would name something no rule can spell, and would then be satisfiable
only by a comment, which is the vacuous shape #325 paid for.

**⚠ And the walk that reads these declarations cannot tell you a rule holds.**
It asks whether each declared column is *named* by a rule on its table — a
word-boundary search over the trigger bodies — which is exactly what lets it
judge a new declaration on the day it is made, and exactly why it goes green
over a branch that refuses nothing. What a declaration here promises is proved
behaviourally, per rule, in the usage app's two transition modules and in
``apps/platform/work/tests/test_a_kind_of_work_declares_how_it_is_sold.py``.
Each of those drives every prohibited write through all three doors and keeps an
admitted move beside it — measured, in #414's case, by gutting the refusal while
leaving the column named: the walk above stayed green and nine subtests of that
module went red.

**A different rule was genuinely deferred, and slice 4 has now paid it.**
``PostingMeasurement``'s whole-record ``DELETE`` condition is cross-table — it
reads the parent posting's costing and pricing statuses, the second of which
landed in slice 4 — and it is enforced since #354 by a ``BEFORE DELETE`` trigger
in ``…/migrations/0041_a_measurement_is_pruned_only_when_it_may_be.py``. But
every column of that record declares ``RECORD_RULE``, which the constant below
puts *outside* ``DATABASE_DEFENDED`` — so it is not a field transition class, it
is not in G19's statement, and slice 4 added it as an extension of the installed
gate rather than by re-owning its row.

⚠ **Which means the walk below does not reach it, and nothing else does
either.** That rule has no ledger entry and no gate manifest row; the only thing
that would notice its absence is
``apps/metering/usage/tests/test_a_measurement_is_pruned_only_when_it_may_be.py``.
Declaring one of that record's columns into a defended class to make this walk
see it would be a false statement about the column, in the module whose whole
subject is that declarations are true.

**There are four transition classes and this module adds none.** ADR-0007 §2
enumerates them and they are the whole vocabulary; `RECORD_RULE` below is not a
fifth, and nothing here should be read as amending that ADR. It is what a column
declares when it has *no* class — so that "declared into none, and here is what
governs it instead" is written down rather than merely absent.

That distinction was load-bearing for more than tidiness. G19's manifest row was
blocked on *"No column is declared into a transition class yet"* until #319
deleted that sentence, and it was true for as long as `DATABASE_DEFENDED` had no
declarers — a `RECORD_RULE` column is one that declined a class rather than took
one, so the measurement child did not make it false.

**#318 made it false, which is what it was waiting for, and #319 moved the row.**
The economic posting declares the first `RESOLVE_ONCE` pair and the first
`FROZEN` column, a trigger installed with them holds all three across every
door, and the row now names the tests that prove it rather than what it is
waiting for.
"""

#: The four classes of ADR-0007 §2, in the order that document states them.
#: A column in one of these makes a promise the database will be made to keep.
FROZEN = "frozen"                #: none after insert
RESOLVE_ONCE = "resolve_once"    #: unresolved/NULL -> one terminal value, once
SET_ONCE = "set_once"            #: NULL -> value, once
PRUNABLE = "prunable"            #: populated -> pruned, after the horizon only

#: What G19 defends — the four, and only the four. A column declared into any of
#: these is a protected column, and slice 3 ships the first one.
DATABASE_DEFENDED = frozenset({FROZEN, RESOLVE_ONCE, SET_ONCE, PRUNABLE})

#: **Not a class — the absence of one, said out loud.**
#:
#: A record whose *whole lifecycle* is a single rule — inserted once, never
#: updated, deleted only under a stated condition — has no per-column
#: transitions to declare, because no column of it ever changes. The posting /
#: measurement split decision (§4) rules exactly this for the measurement child:
#: *"the child needs no transition classes, because it has no lifecycle"*, and
#: *"``UPDATE`` being categorically prohibited is a simpler rule to enforce and
#: to test than any per-column scheme"*. Its own amended table is *"three
#: classes on the posting and one whole-record rule on the child"* — the rule
#: sits beside the classes rather than among them, and so does this constant.
#:
#: A column carrying it has still answered ADR-0007 §2's question, which is what
#: the ADR asks for: *what is allowed to happen to this?* The answer is "nothing
#: this column decides — read the record's rule", and the record states that
#: rule in its docstring.
#:
#: ⚠ **And a record's rule needs its own enforcement and its own tests, because
#: nothing here reaches it.** `columns_declared_into_defended_classes` skips
#: every `RECORD_RULE` column by design, so the gate that judges a declaration
#: on the day it is made cannot judge one of these at all. `PostingMeasurement`'s
#: `DELETE` condition is held by a trigger on its own table and proved by its own
#: module (#354) — three doors, the admitted move, and each condition's cause
#: removed in turn — with no ledger entry and no manifest row behind any of it.
RECORD_RULE = "record_rule"


def columns_declared_into_defended_classes(models):
    """Which of ``models``' declared columns sit in a class G19 defends.

    The one entry point, used by the real check and by its positive control
    alike — a gate whose failing path has never been run is an assertion, not
    evidence. ``models`` is any iterable of objects carrying a
    ``transition_classes`` mapping; anything without one declares nothing and is
    skipped, which is every model in the repository bar the ones that opt in.

    Returns a sorted list of ``(model_name, column, transition_class)``.
    """
    offenders = []
    for model in models:
        declared = getattr(model, "transition_classes", None)
        if not declared:
            continue
        for column, transition_class in declared.items():
            if transition_class in DATABASE_DEFENDED:
                offenders.append((model.__name__, column, transition_class))
    return sorted(offenders)
