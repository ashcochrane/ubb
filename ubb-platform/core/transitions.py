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
actually defend. Nothing *here* installs a trigger, a rule or a ``CHECK`` — this
module is the vocabulary, and the gate that holds a column to what it says lives
with the table.

**A different rule is genuinely deferred, and the comment this replaces
conflated the two.** ``PostingMeasurement``'s whole-record ``DELETE`` condition
is cross-table and unexpressible today, because the second of the two statuses
it reads lands in slice 4. But every column of that record declares
``RECORD_RULE``, which the constant below puts *outside* ``DATABASE_DEFENDED`` —
so it is not a field transition class, it is not in G19's statement, and slice 4
adds it as an extension of the installed gate rather than by re-owning its row.

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
