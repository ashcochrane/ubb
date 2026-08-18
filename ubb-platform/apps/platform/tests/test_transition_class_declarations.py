"""Every column declared into a transition class the database defends, is.

ADR-0007 §2 requires every column of an economically protected record to declare
what may happen to it, and requires the **database** to enforce that declaration
across `save()`, `QuerySet.update()` and raw SQL alike. The enforcement half is
gate G19.

**THIS FILE ASSERTED THE OPPOSITE UNTIL #318, AND IT WAS REPLACED BY ITS
INVERSE RATHER THAN RELAXED.** Until slice 3 there was no enforcement, so the
only honest thing to hold was that **nothing** was declared: a column declared
`FROZEN`, `RESOLVE_ONCE`, `SET_ONCE` or `PRUNABLE` would have been a column
making a promise nothing kept — the exact failure ADR-0007 §2 names when it says
a model-level guard alone is not enforcement, *"the repository has already
shipped one that a production writer bypassed by design"*. That assertion's own
docstring said slice 3 would change it and G19's row together.

Slice 3 declared the first pair and installed the trigger that keeps it, so the
empty-set assertion had to go. **Loosening it — "a column may be declared" — is
the failure it existed to prevent**, because such a test passes whether or not
anything defends anything. The inverse holds the same line from the other side:
declare what you like, and the database had better be holding it.

**The check walks the declarations and names no column.** A list naming this
slice's columns would expire in silence the moment slice 4 declared one of its
own — the vacuity #256 fixed in the gate manifest and #285 shipped again in the
migration ledger. It goes through
`core.transitions.columns_declared_into_defended_classes`, the single entry
point that returns `(model, column, class)` triples, and asserts every triple it
returns is defended.

**Both controls come over.** The vacuity guard flips with the assertion: it used
to prove the walk had read a real declaration, and now proves at least one
column is genuinely defended, so an empty walk cannot report a clean board. The
positive control is unchanged in shape — two synthetic declarers through the
check's real entry point, one of them clean — and it is pointed at a table that
really does carry a rule, so what it demonstrates is the sharp case: a trigger
on the table is not the same thing as a trigger that mentions this column.
"""
import re

from django.apps import apps
from django.db import connection
from django.test import TestCase

from core.transitions import (
    DATABASE_DEFENDED, RECORD_RULE, RESOLVE_ONCE,
    columns_declared_into_defended_classes)


def _declaring_models():
    return [model for model in apps.get_models()
            if getattr(model, "transition_classes", None)]


def declaring_models_by_table():
    """Model name to table, for the models that declare something.

    Public alongside the check it feeds, and for the same reason: the two are
    one call, and handing a caller the check without the map it takes would
    invite a hand-built dictionary that could name the wrong table.

    Reached through the app registry: `apps/platform/**` never imports a product
    (`docs/conventions/coding-standards.md`), and a kernel-side gate whose
    subject is a product model is exactly where that rule gets bent quietly —
    the boundary walker skips `tests/`, so nothing would catch it.

    Built from the DECLARING models alone, and refusing a collision. Django does
    not make a class name unique across apps, and the entry point this gate
    walks returns names rather than models, so two declarers sharing one would
    quietly send the check to look at the wrong table — and it would find the
    wrong answer either way round.
    """
    declaring = _declaring_models()
    tables = {model.__name__: model._meta.db_table for model in declaring}
    assert len(tables) == len(declaring), (
        "two declaring models share a class name; this walk resolves a table by "
        "that name and cannot tell them apart")
    return tables


def _rules_on(table):
    """Everything the database will show us about the rules guarding `table`.

    The trigger definition and the function body both count: a `WHEN` clause
    lives in the first and the refusals in the second, and a column named in
    either is a column the rule can see.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_get_triggerdef(t.oid), p.prosrc "
            "FROM pg_trigger t "
            "JOIN pg_class c ON c.oid = t.tgrelid "
            "JOIN pg_proc p ON p.oid = t.tgfoid "
            "WHERE c.relname = %s AND NOT t.tgisinternal", [table])
        return "\n".join(part for row in cursor.fetchall() for part in row)


def columns_the_database_does_not_defend(triples, tables):
    """The check itself — the real one and the control both come through here.

    A gate whose failing path has never been run is an assertion rather than
    evidence, so there is one implementation and the positive control feeds it
    synthetic declarers.

    **It is public because a third caller needs it, and needs THIS one** (#352).
    `apps/metering/usage/tests/test_a_price_resolves_once.py` proves the
    sentence this check cannot: that a rule NAMING a declared column and a rule
    HOLDING it are different states of the database, and that this search
    reports a clean board over both. A re-implementation of the regex there
    would prove only that two copies of one search agree with each other, so it
    asserts through the search the gate actually runs.
    """
    undefended = []
    for model_name, column, transition_class in triples:
        table = tables.get(model_name)
        rules = _rules_on(table) if table else ""
        if not re.search(rf"\b{re.escape(column)}\b", rules):
            undefended.append((model_name, column, transition_class))
    return sorted(undefended)


class TransitionClassDeclarationsTest(TestCase):

    def _declared(self):
        return columns_declared_into_defended_classes(apps.get_models())

    def test_every_declared_column_is_defended_by_the_database(self):
        self.assertEqual(
            columns_the_database_does_not_defend(self._declared(),
                                                 declaring_models_by_table()),
            [])

    def test_at_least_one_column_is_actually_defended(self):
        """The vacuity guard, flipped along with the assertion above.

        `columns_declared_into_defended_classes` skips anything that declares
        nothing, which is most of the repository. If the declarations were
        removed — a refactor, a moved model, a mapping renamed — the assertion
        above would pass over an empty walk and report a clean board for a tree
        it never looked at, which is how this gate would come to hold nothing at
        exactly the moment it stopped being true.

        It asserts a defended COLUMN and not merely a guarded table, which is a
        distinction with teeth: a table can carry a rule that mentions none of
        the columns declared on it, and that is precisely the case the positive
        control below is built out of.
        """
        declared = self._declared()
        self.assertGreaterEqual(len(declared), 1)
        undefended = columns_the_database_does_not_defend(
            declared, declaring_models_by_table())
        self.assertGreaterEqual(len(declared) - len(undefended), 1)

    def test_the_check_reports_a_violation_when_there_is_one(self):
        """The positive control, through the check's real entry point.

        Two synthetic declarers, one of them clean, so that what comes back is
        the offending column rather than "something, somewhere, was wrong". They
        are pointed at a table that genuinely carries a rule, which makes this
        the case worth controlling for: the table is guarded, and this column
        still is not.
        """
        class Protected:
            transition_classes = {"a_column_no_rule_mentions": RESOLVE_ONCE,
                                  "notes": RECORD_RULE}

        class Clean:
            transition_classes = {"recorded_at": RECORD_RULE}

        guarded_table = declaring_models_by_table()[self._declared()[0][0]]
        self.assertEqual(
            columns_the_database_does_not_defend(
                columns_declared_into_defended_classes([Protected, Clean]),
                {"Protected": guarded_table, "Clean": guarded_table}),
            [("Protected", "a_column_no_rule_mentions", RESOLVE_ONCE)])

    def test_every_declaration_is_one_of_the_known_answers(self):
        """The four classes, or the record rule that is not one of them."""
        known = DATABASE_DEFENDED | {RECORD_RULE}
        for model in _declaring_models():
            with self.subTest(model=model.__name__):
                self.assertLessEqual(
                    set(model.transition_classes.values()), known)
