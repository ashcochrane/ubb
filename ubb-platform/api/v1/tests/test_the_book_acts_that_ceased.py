"""The four acts that replace the three that ceased (#368, spec §19).

Three retired book actions are deleted in this commit — a book was created, a
book was assigned to a customer, a book was published — and **deleting an action
whose act no longer exists is not the rename ADR-004 §2 governs.** A rename
carries an act forward under a new spelling and breaks a reader who was watching
for the old one; these three have no successor to carry forward, because the acts
themselves stopped happening: the entity is replaced and its two halves are
declared separately, the assignment record is deleted, and every change to a book
is a publish whose own three names were already registered.

**NO PART OF THE ONE-TIME PRE-PRODUCTION AUDIT-REGISTRY RESET IS CONSUMED.**
#154 §4.2 defines that exception and #154 §13 / #155 §14 allocate it to slice 8,
for the actions that genuinely ARE renamed. This commit draws against none of it.

⚠ **THE REFUSAL HALF IS NOT HERE, AND WHERE IT IS IS A SWEEP DECISION RATHER
THAN A TASTE ONE.** Asserting that `record()` refuses each of the three means
reaching those three names, and a NEW module carrying them would put their
ledger counts over entries this commit takes to zero — the counts are ceilings
on SPREAD, not only on what is left to fix. So that half lives in
`apps/metering/pricing/tests/test_a_book_of_costs_and_a_book_of_prices_are_two_shapes.py`,
a module already counted for both retired words, where the names are composed
from a prefix spelled once and three ordinary verbs.

What is here is the half whose subject is the ROUTER: which routes write which
action, and which take the audit sweep's exemption. A module under
`apps/**/tests/` importing `api.v1.tests.*` is invisible to the boundary gate
and still wrong (#367), so a router-walk test belongs in `api/v1/tests/`.
"""
from django.test import SimpleTestCase

from api.v1.tests.test_audit_sweep import _EXEMPT, mutating_operations
from apps.platform.audit.actions import AUDIT_ACTIONS

#: What replaces the three: one action per record per kind of act.
THE_ACTS_THAT_ARRIVED = (
    "pricing_book.declared",
    "pricing_book.withdrawn",
    "cost_book.declared",
    "cost_book.withdrawn",
)


class TheFourNewActsAreGovernanceTest(SimpleTestCase):
    """Declaring a book and withdrawing one, per kind of book.

    ⚠ **FOUR WHERE THE TICKET SAID TWO, AND THE ARITHMETIC IS THE REGISTRY'S
    OWN RULE.** That rule — one action per record per kind of act, *"split now,
    when it is free"* — is the one the ticket cites, and this commit creates
    TWO records. A Pricing Book and a cost book have different columns,
    different products gating them (a cost book is metering; a Pricing Book is
    billing) and different readers. A shared noun would be the first place in
    this registry where one action spans two record types, and it would put a
    governance reader asking *"when did this tenant withdraw a PRICING book"*
    back to reading `resource_type` — which is what the rule refuses. Splitting
    later is the rename ADR-004 §2 calls a breaking change, and it is free now.
    """

    def test_all_four_are_registered_and_distinct(self):
        self.assertEqual(len(set(THE_ACTS_THAT_ARRIVED)), 4)
        for name in THE_ACTS_THAT_ARRIVED:
            with self.subTest(name):
                self.assertIn(name, AUDIT_ACTIONS)

    def test_declaring_and_withdrawing_are_not_one_act(self):
        """The split the registry's rule asks for, said as a property.

        A governance reader asking when a book stopped existing must not have
        to read metadata to find out.
        """
        for noun in ("pricing_book", "cost_book"):
            with self.subTest(noun):
                self.assertIn(f"{noun}.declared", AUDIT_ACTIONS)
                self.assertIn(f"{noun}.withdrawn", AUDIT_ACTIONS)

    def test_the_two_records_do_not_share_a_noun(self):
        """The half a generic name would quietly lose."""
        self.assertNotIn("book.declared", AUDIT_ACTIONS)
        self.assertNotIn("book.withdrawn", AUDIT_ACTIONS)


class NoneOfTheFourRoutesTakesTheExemptionTest(SimpleTestCase):
    """They register names rather than joining the audit sweep's carve.

    Declaring a book decides what a tenant may be charged from and withdrawing
    one takes a catalogue away; both are governance in exactly the sense every
    pair in that registry is. The exemption list is for TELEMETRY — usage
    ingestion, the spend start-gate — and nothing here belongs on it.

    ⚠ Read the list DIRECTLY rather than trusting the sweep's own count, which
    would stay green if a route joined the carve while another left it.
    """

    BOOK_PATHS = (
        ("POST", "/metering/pricing/pricing-books"),
        ("DELETE", "/metering/pricing/pricing-books/{book_id}"),
        ("POST", "/metering/pricing/cost-books"),
        ("DELETE", "/metering/pricing/cost-books/{book_id}"),
    )

    def test_the_walker_sees_all_four(self):
        """The vacuity guard: a path spelled wrongly here would make every
        assertion below true by naming no route at all."""
        seen = {(method, path) for method, path, _ in mutating_operations()}

        for entry in self.BOOK_PATHS:
            with self.subTest(entry):
                self.assertIn(entry, seen)

    def test_none_of_them_is_exempt(self):
        for entry in self.BOOK_PATHS:
            with self.subTest(entry):
                self.assertNotIn(entry, _EXEMPT)

    def test_each_of_them_declares_an_action(self):
        by_route = {(method, path): view_func
                    for method, path, view_func in mutating_operations()}

        for entry in self.BOOK_PATHS:
            with self.subTest(entry):
                declared = getattr(by_route[entry], "_audit_actions", None)
                self.assertTrue(declared, entry)
                for name in declared:
                    self.assertIn(name, THE_ACTS_THAT_ARRIVED)
