"""A customer price becomes known only through its door (#557).

`price_resolution.resolve_customer_price` is the one statement in production
that moves a posting's price from `unknown` to `known`. Until #557 that was a
sentence in its docstring: the price pair's rule (`trg_posting_price_transitions`,
as `usage/0039` installed it and `usage/0046` widened it, before the cutover
squash, #190) stopped a second writer CORRUPTING a resolved price, but it
admitted the first resolution from anyone, so a second writer would have
decided "this price is now known" somewhere the door's tests never look.

The cost side answers the same question with an `ast` walk over the tree. The
owner ruled the price side's answer is a **behavioural or database** one, and
never a second tree walk (#557, `5785065807`). So the table holds it:
`trg_posting_price_transitions` admits the move only on a statement the door
marked (`usage/0049`'s rule before the cutover, #190; the usage rules
migration's `POSTING_PRICE_TRANSITIONS` now), and this module plants the
second writer and watches it refused, through each of ADR-0007 §2's three
doors, with the posting still `unknown` afterwards. The rule's REVERSE is
proven centrally, with every other rule's
(`apps/platform/tests/test_the_database_rules_are_carried.py`).

**The door resolving is the control.** A rule refusing every resolution would
satisfy each refusal below and leave every unknown price unknown forever, which
is worse than the defect; the first class is the evidence it is not that rule.

**Each refusal is read for what it says.** The transition rule beside it refuses
in the same SQLSTATE and also names `resolve_once` and the price column, so a
refusal is accepted here only if it carries the door's own sentence too — a
test that could not tell the two apart would be evidence that the table refused
something, not that it refused a second writer.
"""
import re
from unittest.mock import patch

from django.db import DataError, IntegrityError, connection, transaction
from django.db.models import QuerySet
from django.test import TestCase

from apps.metering.pricing.services.price_resolution import (
    PRICE_DOOR_MARK, PRICE_DOOR_SETTING, PriceResolution,
    marked_as_the_price_door, resolve_customer_price)
from apps.metering.pricing.tests._helpers import database_rules_guarding
from apps.metering.usage.models import Posting
from apps.metering.usage.tests._helpers import (
    DOORS, committed_posting, through_the_queryset)
from core.transitions import RESOLVE_ONCE
from core.vocabulary import PRICING_STATUS_KNOWN, PRICING_STATUS_UNKNOWN

PRICE = "billed_cost_micros"
STATUS = "pricing_status"

#: The whole legal resolution — the move the transition rule admits. Anything
#: refusing it below is refusing WHO made it, never what was made.
RESOLUTION = {PRICE: 4_200, STATUS: PRICING_STATUS_KNOWN}

#: What only the door's refusal says. The transition rule's own refusal names
#: `resolve_once` and the column too, so those two alone cannot tell them apart.
THE_DOORS_REFUSAL = "becomes known only through its door"

#: The rule that holds the door, by the name the catalogue knows it under.
DOOR_RULE = "trg_posting_price_transitions"


def _unknown():
    """A price UBB could not resolve — the one state a resolution starts in."""
    return committed_posting(**{PRICE: None, STATUS: PRICING_STATUS_UNKNOWN})


def _as_stored(posting):
    """The amount and status the table holds, read fresh.

    Never `refresh_from_db` on the instance a door wrote through: `save()`
    leaves the instance carrying what it tried to write, and a pin reading the
    response of a write rather than the stored row is the pin that misses it.
    """
    return Posting.objects.filter(pk=posting.pk).values_list(
        PRICE, STATUS).get()


def _refusal(write):
    """The message Postgres refused `write` with, or `None` if it landed."""
    try:
        with transaction.atomic():
            write()
    except IntegrityError as refusal:
        return str(refusal)
    return None


class TheDoorResolvesAnUnknownPriceTest(TestCase):
    """The admitted move, and the refusals below are worthless without it."""

    def test_the_door_resolves_an_unknown_price(self):
        posting = _unknown()

        outcome = resolve_customer_price(posting_id=posting.pk,
                                         billed_cost_micros=4_200)

        self.assertIs(outcome, PriceResolution.RESOLVED)
        self.assertEqual(_as_stored(posting), (4_200, PRICING_STATUS_KNOWN))


class ASecondWriterIsRefusedAtTheTableTest(TestCase):
    """The planted second writer, through every door, and what it leaves."""

    def assert_refused_by_the_door_rule(self, message):
        self.assertIsNotNone(message, "a second writer resolved a price")
        self.assertIn(THE_DOORS_REFUSAL, message)
        self.assertIn(RESOLVE_ONCE, message)
        self.assertIn(PRICE, message)

    def test_a_second_writer_is_refused_through_every_door(self):
        """The legal move, made by anyone else, is refused — and nothing moved.

        Each door writes exactly what the door would: the amount and `known`
        in one statement, from `unknown`. The transition rule admits that; only
        the door rule can be what refuses it.
        """
        for name, door in DOORS:
            with self.subTest(door=name):
                posting = _unknown()

                message = _refusal(lambda: door(posting, **RESOLUTION))

                self.assert_refused_by_the_door_rule(message)
                self.assertEqual(_as_stored(posting),
                                 (None, PRICING_STATUS_UNKNOWN))

    def test_a_mark_naming_anything_else_is_not_the_door(self):
        """The setting has one value that is the door, and only that one.

        A writer that sets the setting to anything else — its own name, an
        empty string — is a second writer still.
        """
        for mark in ("a_second_writer", ""):
            with self.subTest(mark=mark):
                posting = _unknown()

                def marked_otherwise():
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT set_config(%s, %s, true)",
                                       [PRICE_DOOR_SETTING, mark])
                    through_the_queryset(posting, **RESOLUTION)

                self.assert_refused_by_the_door_rule(
                    _refusal(marked_otherwise))
                self.assertEqual(_as_stored(posting),
                                 (None, PRICING_STATUS_UNKNOWN))

    def test_the_door_leaves_no_mark_behind(self):
        """A writer after the door, in the SAME transaction, is still refused.

        The mark is transaction-local, and a run resolving two hundred prices
        is one transaction: a mark the door left standing would turn every
        statement after its first into a door. This test case is one
        transaction throughout, which is the case that matters.
        """
        first, second = _unknown(), _unknown()
        resolve_customer_price(posting_id=first.pk, billed_cost_micros=1)

        message = _refusal(lambda: through_the_queryset(second, **RESOLUTION))

        self.assert_refused_by_the_door_rule(message)
        self.assertEqual(_as_stored(second), (None, PRICING_STATUS_UNKNOWN))


class AFailedResolutionLeavesNoMarkBehindTest(TestCase):
    """The door raising is the door finishing, as far as the mark goes (#557;
    the consultant's review of #618): a writer after it, in the same outer
    transaction, is refused all the same — whichever way it failed."""

    def assert_a_writer_after_it_is_refused(self):
        second = _unknown()
        message = _refusal(lambda: through_the_queryset(second, **RESOLUTION))
        self.assertIsNotNone(message, "the mark outlived a failed resolution")
        self.assertIn(THE_DOORS_REFUSAL, message)
        self.assertEqual(_as_stored(second), (None, PRICING_STATUS_UNKNOWN))

    def test_a_resolver_that_raises_under_the_mark_clears_it(self):
        """Python raising before the statement runs. The door's own savepoint
        is rolled back on the way out, and the mark with it."""
        first = _unknown()

        with patch.object(QuerySet, "update",
                          side_effect=RuntimeError("the resolution fails")):
            with self.assertRaises(RuntimeError):
                resolve_customer_price(posting_id=first.pk,
                                       billed_cost_micros=1)

        self.assertEqual(_as_stored(first), (None, PRICING_STATUS_UNKNOWN))
        self.assert_a_writer_after_it_is_refused()

    def test_the_mark_itself_is_cleared_where_no_savepoint_would(self):
        """The marker's own guarantee, for a caller with no savepoint round it
        — the test helper, the measurement script: Python raising under the
        mark leaves the transaction usable, and the mark is cleared on the way
        out, not left to a rollback that will not come."""
        with self.assertRaises(RuntimeError):
            with marked_as_the_price_door():
                raise RuntimeError("raised under the mark")

        self.assert_a_writer_after_it_is_refused()

    def test_a_statement_the_database_refuses_takes_the_mark_with_it(self):
        """The database refusing the marked statement itself — an amount past
        the money column. The door's savepoint is rolled back and the mark
        with it; the failure is reported as ITSELF, not as a clear attempted
        in an aborted transaction."""
        first = _unknown()

        with self.assertRaises(DataError):
            resolve_customer_price(posting_id=first.pk,
                                   billed_cost_micros=2 ** 63)

        self.assertEqual(_as_stored(first), (None, PRICING_STATUS_UNKNOWN))
        self.assert_a_writer_after_it_is_refused()


class TheRuleSpellsTheDoorsOwnMarkTest(TestCase):
    """The rule and the door agree on ONE spelling of the mark, asked of the
    rule the database holds.

    The door sets `PRICE_DOOR_SETTING` to `PRICE_DOOR_MARK`; the rule compares
    the same setting with the same value, in SQL text Python never imports. A
    rename on one side alone would make every price unresolvable (the door
    refused) or — worse — leave a mark nothing reads. The behavioural cases
    above would catch the first; this names the agreement itself, on the
    installed function body rather than on the text of a migration file.
    """

    def test_the_installed_rule_compares_the_setting_the_door_sets_with_its_mark(self):
        (body,) = [source for name, _, source
                   in database_rules_guarding(Posting._meta.db_table)
                   if name == DOOR_RULE]

        self.assertRegex(
            body,
            rf"current_setting\('{re.escape(PRICE_DOOR_SETTING)}', true\)"
            rf"\s+IS DISTINCT FROM '{re.escape(PRICE_DOOR_MARK)}'")
