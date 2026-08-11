"""Declared transition classes — what a column is allowed to become.

ADR-0007 §2 rules that no record claims to be "immutable" as a whole: **every
column is declared into exactly one class, and the database enforces the
permitted transition** regardless of which door the write came through. This
module is the vocabulary that declaration is written in — a model states its
classes in a ``transition_classes`` mapping beside its fields, so that the
question "what is allowed to happen to this?" is answered at model-definition
time. ADR-0007's Consequences names that as both the cost and the point.

**Declaring is not enforcing, and today nothing here enforces anything.**
Database enforcement is gate G19, which is ``owned_by_slice_3`` and whose
cross-table condition is unexpressible before slice 4 — one of the two statuses
it must read lands in slice 3 and the other in slice 4. Nothing in this module
installs a trigger, a rule or a ``CHECK``; it lets a column say what it is so
that the gate which will hold it to that has a subject when it arrives.

``DATABASE_DEFENDED`` is therefore the load-bearing name here. It is the set of
classes G19 will defend, and while G19's manifest row still reads *"No column is
declared into a transition class yet"*, no column may be declared into one of
them — see ``RECORD_RULE`` for the alternative a whole-record lifecycle takes.
"""

#: The four classes of ADR-0007 §2, in the order that document states them.
#: A column in one of these makes a promise the database will be made to keep.
FROZEN = "frozen"                #: none after insert
RESOLVE_ONCE = "resolve_once"    #: unresolved/NULL -> one terminal value, once
SET_ONCE = "set_once"            #: NULL -> value, once
PRUNABLE = "prunable"            #: populated -> pruned, after the horizon only

#: What G19 defends. A column declared into any of these is a protected column,
#: and slice 3 ships the first one.
DATABASE_DEFENDED = frozenset({FROZEN, RESOLVE_ONCE, SET_ONCE, PRUNABLE})

#: Not one of the four, and deliberately outside ``DATABASE_DEFENDED``.
#:
#: A record whose *whole lifecycle* is a single rule — inserted once, never
#: updated, deleted only under a stated condition — has no per-column
#: transitions to declare, because no column of it ever changes. The posting /
#: measurement split decision (§4) rules exactly this for the measurement child:
#: *"the child needs no transition classes, because it has no lifecycle"*, and
#: *"``UPDATE`` being categorically prohibited is a simpler rule to enforce and
#: to test than any per-column scheme"*.
#:
#: So its columns are declared, as ADR-0007 §2 requires every column to be, and
#: what they are declared into is the record's own rule rather than a class of
#: their own. The record states that rule in its docstring; this constant is how
#: each column points at it.
RECORD_RULE = "record_rule"

#: Every class a column may be declared into.
TRANSITION_CLASSES = DATABASE_DEFENDED | {RECORD_RULE}


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
