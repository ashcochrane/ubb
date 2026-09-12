"""The webhook module holds the registry's catalogue by reference and says
whether a proposed subscription names only published events (#464, slice 6
§16–§17 — the `webhook_event_type` SDK payment).

An integrator branches on a constant, reached BY MODULE
(`docs/conventions/sdk-wrap.md` §Canonical vocabulary: `from ubb import
vocabulary`), and checks a subscription against the same closed set the
server's `enum` states — plus the one selector that is not a name.
"""
import ast
import re
import unittest
from pathlib import Path

import ubb.vocabulary as vocabulary
import ubb.webhooks as webhooks
from ubb.webhooks import EVENT_SELECTORS, WILDCARD, unpublished_event_types

#: Every generated per-name handle for the concept, derived from the artifact
#: rather than listed — a thirty-eighth registry value is a red line here,
#: not a silent partial payment.
EVENT_TYPE_NAMES = frozenset(
    name for name in vars(vocabulary)
    if name.startswith("WEBHOOK_EVENT_TYPE_") and not name.endswith("_VALUES"))


class TheModuleHoldsTheCatalogueTest(unittest.TestCase):
    def test_there_is_one_constant_per_published_name_and_the_set_is_theirs(self):
        """37 constants, one per name, whose values ARE the closed set — so an
        integrator never types an event name."""
        values = {getattr(vocabulary, name) for name in EVENT_TYPE_NAMES}
        self.assertEqual(values, vocabulary.WEBHOOK_EVENT_TYPE_VALUES)
        self.assertEqual(len(EVENT_TYPE_NAMES), len(values))
        self.assertGreaterEqual(len(values), 37)
        # And each constant is named for its value under the generator's rule.
        for name in EVENT_TYPE_NAMES:
            expected = "WEBHOOK_EVENT_TYPE_" + re.sub(
                r"[^0-9A-Za-z]+", "_", getattr(vocabulary, name)).upper()
            self.assertEqual(name, expected)

    def test_the_selectors_are_the_catalogue_plus_the_wildcard_and_nothing_else(
            self):
        """Not an alias of the generated set: what a SUBSCRIPTION may name is
        every published event and the wildcard, which the registry
        deliberately does not list."""
        self.assertEqual(EVENT_SELECTORS,
                         vocabulary.WEBHOOK_EVENT_TYPE_VALUES | {WILDCARD})
        self.assertNotIn(WILDCARD, vocabulary.WEBHOOK_EVENT_TYPE_VALUES)
        self.assertEqual(WILDCARD, "*")

    def test_the_module_reaches_the_vocabulary_by_module_and_re_exports_nothing(
            self):
        """Read the import statements, not the values: a literal that
        happened to agree would satisfy an equality and is exactly the debt
        this pays, and a `from ubb.vocabulary import WEBHOOK_EVENT_TYPE_*`
        here would be the re-export layer the wrap convention refuses."""
        tree = ast.parse(Path(webhooks.__file__).read_text(encoding="utf-8"))
        by_name = {
            alias.name for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "ubb.vocabulary"
            for alias in node.names}
        self.assertEqual(by_name, set())
        by_module = any(
            isinstance(node, ast.ImportFrom) and node.module == "ubb"
            and any(alias.name == "vocabulary" for alias in node.names)
            for node in ast.walk(tree))
        self.assertTrue(by_module)
        reached = {
            node.attr for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "vocabulary"}
        # The whole-set handle carries every value the generator names.
        self.assertIn("WEBHOOK_EVENT_TYPE_VALUES", reached)

    def test_the_catalogue_is_documented_where_a_subscriber_reads(self):
        self.assertIn("WEBHOOK_EVENT_TYPE_", webhooks.__doc__)
        self.assertIn("EVENT_SELECTORS", webhooks.__doc__)
        self.assertIn("unpublished_event_types", webhooks.__doc__)


class AProposedSubscriptionIsCheckedTest(unittest.TestCase):
    def test_a_valid_subscription_names_nothing_unpublished(self):
        proposed = [vocabulary.WEBHOOK_EVENT_TYPE_USAGE_RECORDED,
                    vocabulary.WEBHOOK_EVENT_TYPE_CUSTOMER_STOPPED,
                    vocabulary.WEBHOOK_EVENT_TYPE_WALLET_POLICY_SOFT_FLOOR_CROSSED]
        self.assertEqual(unpublished_event_types(proposed), frozenset())

    def test_every_published_name_is_accepted_alone_and_together(self):
        for name in sorted(vocabulary.WEBHOOK_EVENT_TYPE_VALUES):
            self.assertEqual(unpublished_event_types([name]), frozenset(), name)
        self.assertEqual(
            unpublished_event_types(vocabulary.WEBHOOK_EVENT_TYPE_VALUES),
            frozenset())

    def test_an_unpublished_name_is_reported_and_the_published_ones_are_not(self):
        """A typo, and a name of the right shape that UBB has never published:
        both come back, and only they do."""
        proposed = ["usage.recieved", vocabulary.WEBHOOK_EVENT_TYPE_USAGE_RECORDED,
                    "wallet.credited"]
        self.assertEqual(unpublished_event_types(proposed),
                         frozenset({"usage.recieved", "wallet.credited"}))

    def test_the_wildcard_subscription_names_nothing_unpublished(self):
        """`["*"]` is every event, current and future; beside names it is
        still a selector and still published."""
        self.assertEqual(unpublished_event_types([WILDCARD]), frozenset())
        self.assertEqual(
            unpublished_event_types(
                [WILDCARD, vocabulary.WEBHOOK_EVENT_TYPE_REFUND_REQUESTED]),
            frozenset())

    def test_the_answer_is_a_set_of_the_offending_names_not_a_verdict(self):
        """Any iterable in, a frozenset out, so the caller can say WHICH."""
        answer = unpublished_event_types(("usage.recieved", "usage.recieved"))
        self.assertIsInstance(answer, frozenset)
        self.assertEqual(answer, frozenset({"usage.recieved"}))
        self.assertEqual(unpublished_event_types([]), frozenset())


if __name__ == "__main__":
    unittest.main()
