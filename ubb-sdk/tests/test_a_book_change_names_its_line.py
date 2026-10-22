"""The contract's first discriminated union, through the generated SDK (#553).

The publish act's change body is one of two bodies told apart by `line`, and a
diff row answers the same union back. The publish act stays generated-only, so
what the SDK owes is that its generated models carry the union: each body
parses into its own model, round-trips to the dict it came from, and a diff row
of each kind comes back as its own row model.

⚠ THE GENERATOR DOES NOT READ THE `discriminator` MAPPING. It tries the members
in order, and a member's `from_dict` refuses a `line` other than its own
`const` — so the dispatch is correct because each body checks its own tag,
which is what the last case below holds.
"""
import unittest

from ubb._core.models.book_agreed_price_change_diff_out import (
    BookAgreedPriceChangeDiffOut)
from ubb._core.models.book_agreed_price_change_in import BookAgreedPriceChangeIn
from ubb._core.models.book_publish_in import BookPublishIn
from ubb._core.models.book_publish_out import BookPublishOut
from ubb._core.models.book_rate_change_diff_out import BookRateChangeDiffOut
from ubb._core.models.book_rate_change_in import BookRateChangeIn
from ubb._core.models.paginated_agreed_prices import PaginatedAgreedPrices

A_RATE_CHANGE = {"line": "rate", "kind": "reprice",
                 "measurement_key": "input_tokens", "provider": "",
                 "event_type": "", "task_type": "", "subtask_type": "",
                 "grouping_fields": {}, "rate_per_unit_micros": 2}
AN_AGREED_PRICE_CHANGE = {"line": "agreed_price", "kind": "add",
                          "task_type": "transcode",
                          "agreed_price_micros": 8_000_000}


def a_draft(diff):
    return {"id": "p1", "book_id": "b1", "declaration_status": "draft",
            "effective_at": "2026-10-21T00:00:00+00:00", "published_at": None,
            "actor_kind": "", "actor_id": "", "actor_display": "",
            "opened_rule_ids": [], "closed_rule_ids": [],
            "opened_agreed_price_ids": [], "closed_agreed_price_ids": [],
            "diff": diff, "diff_unavailable_reason": None}


class ABookChangeNamesItsLineTest(unittest.TestCase):

    def test_each_body_parses_into_its_own_model(self):
        body = BookPublishIn.from_dict(
            {"changes": [A_RATE_CHANGE, AN_AGREED_PRICE_CHANGE]})

        rate, price = body.changes
        self.assertIsInstance(rate, BookRateChangeIn)
        self.assertIsInstance(price, BookAgreedPriceChangeIn)
        self.assertEqual(price.task_type, "transcode")
        self.assertEqual(price.agreed_price_micros, 8_000_000)

    def test_a_publish_body_round_trips_to_what_it_came_from(self):
        changes = [A_RATE_CHANGE, AN_AGREED_PRICE_CHANGE]

        self.assertEqual(
            BookPublishIn.from_dict({"changes": changes}).to_dict()["changes"],
            changes)

    def test_a_diff_row_of_each_kind_comes_back_as_its_own_row(self):
        draft = BookPublishOut.from_dict(a_draft([
            {"line": "rate", "kind": "retire",
             "measurement_key": "input_tokens", "provider": "",
             "event_type": "", "task_type": "", "subtask_type": "",
             "grouping_fields": {}, "before": None, "after": None},
            {"line": "agreed_price", "kind": "reprice",
             "task_type": "transcode",
             "before": {"agreed_price_micros": 8_000_000},
             "after": {"agreed_price_micros": 9_000_000}},
        ]))

        rate, price = draft.diff
        self.assertIsInstance(rate, BookRateChangeDiffOut)
        self.assertIsInstance(price, BookAgreedPriceChangeDiffOut)
        self.assertEqual(price.after.agreed_price_micros, 9_000_000)

    def test_a_body_refuses_a_line_that_is_not_its_own(self):
        with self.assertRaisesRegex(ValueError, "line must match const"):
            BookRateChangeIn.from_dict(dict(AN_AGREED_PRICE_CHANGE,
                                            measurement_key="input_tokens"))


class TheAgreedPricesReadIsTypedTest(unittest.TestCase):
    """The read's models (#553 story 26): generated, so an integrator checking
    configuration in code gets each line typed with no wrapper."""

    def test_a_page_of_agreed_prices_parses_into_typed_lines(self):
        page = PaginatedAgreedPrices.from_dict({
            "data": [{"id": "l1", "book_id": "b1", "lineage_id": "g1",
                      "task_type": "transcode",
                      "agreed_price_micros": 8_000_000,
                      "valid_from": "2026-10-21T00:00:00+00:00",
                      "valid_to": None}],
            "next_cursor": None, "has_more": False})

        (line,) = page.data
        self.assertEqual(line.task_type, "transcode")
        self.assertEqual(line.agreed_price_micros, 8_000_000)
        self.assertIsNone(line.valid_to)
