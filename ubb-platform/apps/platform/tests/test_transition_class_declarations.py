"""No column is declared into a transition class the database defends.

ADR-0007 §2 requires every column of an economically protected record to declare
what may happen to it, and requires the **database** to enforce that declaration
across `save()`, `QuerySet.update()` and raw SQL alike. The enforcement half is
gate G19, which is `owned_by_slice_3` and blocked on there being a subject: its
manifest note reads *"Slice 3 is the first slice with protected columns, not the
last."*

That note is a claim about the tree, and this is what keeps it true. A column
declared `FROZEN`, `RESOLVE_ONCE`, `SET_ONCE` or `PRUNABLE` today would be a
column making a promise nothing keeps — the exact failure ADR-0007 §2 names when
it says a model-level guard alone is not enforcement, *"the repository has
already shipped one that a production writer bypassed by design"*.

The measurement child (#270) is the first record to declare its classes at all,
and it declares every column into the record rule instead: it has no per-column
lifecycle, because no column of it ever changes. When slice 3 ships the first
`RESOLVE_ONCE` pair it will change G19's row and this file together — the point
is that it cannot happen silently.

**The gate ships with a positive control and a vacuity guard**, because an
absence assertion that has never been shown to fail is an assertion, not
evidence, and one that walks nothing is worse than none at all: the board stays
green either way.
"""
from django.apps import apps
from django.test import SimpleTestCase

from core.transitions import (
    DATABASE_DEFENDED, FROZEN, RECORD_RULE, RESOLVE_ONCE,
    columns_declared_into_defended_classes)

#: The first record to declare anything, named as a STRING and reached through
#: the app registry. `apps/platform/**` never imports a product
#: (`docs/conventions/coding-standards.md`), and a kernel-side gate whose
#: subject is a product model is exactly where that rule gets bent quietly —
#: the boundary walker skips `tests/`, so nothing would catch it.
FIRST_DECLARER = "PostingMeasurement"


def _declaring_models():
    return [model for model in apps.get_models()
            if getattr(model, "transition_classes", None)]


class TransitionClassDeclarationsTest(SimpleTestCase):

    def test_no_column_is_declared_into_a_class_the_database_defends(self):
        self.assertEqual(
            columns_declared_into_defended_classes(apps.get_models()), [])

    def test_the_check_read_a_real_declaration(self):
        """The vacuity guard.

        `columns_declared_into_defended_classes` skips anything that declares
        nothing, which is every model in the repository bar one. If that one
        stopped declaring — a refactor, a moved model, a mapping renamed — the
        assertion above would pass over an empty walk and report a clean board
        for a tree it never looked at.
        """
        declaring = _declaring_models()
        self.assertIn(FIRST_DECLARER, {model.__name__ for model in declaring})
        columns = {column for model in declaring
                   for column in model.transition_classes}
        self.assertGreaterEqual(len(columns), 4)

    def test_the_check_reports_a_violation_when_there_is_one(self):
        """The positive control, through the check's real entry point.

        Two synthetic declarers, one of them clean, so that what comes back is
        the offending column rather than "something, somewhere, was wrong".
        """
        class Protected:
            transition_classes = {"provider_cost_micros": RESOLVE_ONCE,
                                  "currency": FROZEN,
                                  "notes": RECORD_RULE}

        class Clean:
            transition_classes = {"recorded_at": RECORD_RULE}

        self.assertEqual(
            columns_declared_into_defended_classes([Protected, Clean]),
            [("Protected", "currency", FROZEN),
             ("Protected", "provider_cost_micros", RESOLVE_ONCE)])

    def test_every_declaration_is_one_of_the_known_answers(self):
        """The four classes, or the record rule that is not one of them."""
        known = DATABASE_DEFENDED | {RECORD_RULE}
        for model in _declaring_models():
            with self.subTest(model=model.__name__):
                self.assertLessEqual(
                    set(model.transition_classes.values()), known)
