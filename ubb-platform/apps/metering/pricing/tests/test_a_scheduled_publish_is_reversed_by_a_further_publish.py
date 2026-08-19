"""A scheduled publish is reversed by a further publish, and the diary never
rewrites (#360, spec §9 — rulings 3 and 14b).

**THE MECHANISM THE PRICING-VERSIONS DECISION WROTE IS NOT AVAILABLE, AND THAT
IS A DATABASE REFUSAL RATHER THAN A PREFERENCE.** That document cancels a
pending publish by *deleting the rows whose moment is still in the future and
reopening their predecessors' effective-to*. The reopen is a value-to-null
write and `Rate.valid_to` is declared `SET_ONCE`, held by a trigger with no way
to ask whether the period has reported.

**THE RULING: A CANCELLATION IS A FURTHER PUBLISH.**

```
publish P1, effective T   rule A closed at T        (null -> value, once)
                          rule B opens  at T

the tenant reverses:
publish P2, effective T   rule B closed at T        (null -> value, once)
                          rule A' opens at T        (a new version of A's rule)
```

Every write is an INSERT or a once-only null-to-value close. No forbidden
transition occurs and **no row is reopened**. Rule B's window `[T, T)` is empty
and resolves for no instant, which is correct — it never took effect.

**WHAT EACH CLASS BELOW IS FOR.**

* *A cancellation is a further publish* — the two writes the reversal makes,
  read off the rows as a before/after and off the statements as their shapes.
  Nothing is deleted and nothing is reopened, and the reversed rule answers at
  no instant at all.
* *The history is complete* — two publishes an auditor reads, with their actors
  and their instants, **from the records alone**. Delete-and-reopen erases the
  fact that the decision was ever made; this is the case that says it does not.
* *A receipt written before the schedule survives* — the rule a stored receipt
  points at still exists and is still closed at the same instant. Re-creating
  rows would have broken the pointer.
* *A series composes* — ruling 14b. The one-pending limit is gone, and three
  boundaries outstanding at once compose as three windows.
* *A publish sits at or after the book's own latest boundary* — the constraint
  that replaces the limit. At it is accepted, which is what makes the reversal
  above legal; before it is refused with a named code.
* *The database refuses the earlier case regardless* — the service guard is a
  restatement of a rule the database holds, and this is where that is measured
  rather than claimed.
* *A discarded draft costs nothing* — the cheap path, and the reason most
  changes of mind never reach any of the above.

**THE RETIRED WORDS THIS MODULE NEVER SPELLS.** The rule table's own name and
the container's pointer both carry ledger entries that are ceilings as well as
floors, and the table is addressed here through `Rate._meta.db_table` rather
than written out — which is also why a statement-shape assertion can tell the
rule's table from the container's, since one name is a prefix of the other. A
book's rules are read through its reverse relation, every book and rule is
built through `_helpers`, and a stored receipt is addressed through
`Posting.RECEIPT_COLUMN`.
"""

import inspect
from datetime import timedelta
from uuid import uuid4

from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.metering.pricing.models import (
    CHANGE_RETIRE, PricingBookPublish, Rate)
from apps.metering.pricing.services.book_service import (
    BookService, latest_scheduled_boundary)
from apps.metering.pricing.tests._helpers import (
    DOORS,
    FIRST,
    FOURTH,
    SCHEDULING_EVENT_TYPE,
    SCHEDULING_PROVIDER,
    SCHEDULING_QUANTITY,
    SECOND,
    THE_TERM,
    THIRD,
    AForwardDatingBookMixin,
    cost_book,
    declares_a_markup,
    rate_in_default_book,
    rules_snapshot,
    through_raw_sql,
)
from apps.metering.usage.models import Posting
from apps.platform.audit.actors import member_actor
from core.problems import Problem
from core.transitions import SET_ONCE

#: How far ahead the fixtures date a change. Comfortably inside the platform's
#: horizon, and far enough that no case here could pass by the boundary having
#: quietly arrived while the test ran.
A_MONTH = timedelta(days=30)

#: The narrowest instant either side of a boundary, so "resolves for no
#: instant" is asserted at the two moments an empty window could plausibly
#: cover rather than at two moments nothing covers anyway.
ONE_MICROSECOND = timedelta(microseconds=1)

#: The coded refusal ruling 14b's constraint answers with. Named here so every
#: case below asserts the CODE rather than the status — a 422 on this route
#: already means three other things.
BEFORE_THE_BOUNDARY = "effective_at_before_scheduled_boundary"

#: A second declared quantity in the same book, so a publish can name a rule
#: that has no boundary of its own. That is the only way to reach the
#: book-wide floor: every other earlier-dated publish is caught by the refusal
#: that names the rule already scheduled to close.
ANOTHER_QUANTITY = "completion_tokens"


def _writes_against_the_rules_table(captured):
    """Every statement the rule table was written by, as its leading verb.

    Addressed through the model's own table name, quoted the way the driver
    quotes it: the container's table name has the rule's as a PREFIX, so a bare
    substring test would count the book's version bump as a write to a rule.
    """
    table = f'"{Rate._meta.db_table}"'
    return [
        query["sql"].split(None, 1)[0].upper()
        for query in captured.captured_queries
        if table in query["sql"]
        and query["sql"].split(None, 1)[0].upper() in {"INSERT", "UPDATE",
                                                       "DELETE"}
    ]


class ACancellationIsAFurtherPublishTest(AForwardDatingBookMixin, TestCase):
    """The reversal, written down as what it does to the rows.

    A rise is scheduled and then reversed at the same instant. Both acts are
    publishes, and the second one's whole claim is that it took nothing back —
    it added.
    """

    def setUp(self):
        super().setUp()
        self.boundary = timezone.now() + A_MONTH
        self.rise = self.publish_at(self.boundary, SECOND)
        self.raised = Rate.objects.get(pk=self.rise.opened_rule_ids[0])

    def _reverse(self):
        return self.publish_at(self.boundary, FIRST)

    def test_the_reversal_wrote_one_insert_and_one_null_to_value_close(self):
        """AC 1 — the two statements, and neither of them takes anything back.

        Asserted twice over, because either half alone is satisfiable by the
        mechanism this ruling rejects. The STATEMENT SHAPES rule out a delete;
        the BEFORE/AFTER over every row rules out a reopen and a moved close,
        which a statement shape cannot see.
        """
        before = {rule["id"]: rule for rule in rules_snapshot(self.book)}

        with CaptureQueriesContext(connection) as captured:
            self._reverse()

        self.assertEqual(_writes_against_the_rules_table(captured),
                         ["UPDATE", "INSERT"])
        after = {rule["id"]: rule for rule in rules_snapshot(self.book)}
        self.assertEqual(len(after), len(before) + 1)
        # Nothing was deleted: every row that existed still does.
        self.assertEqual(set(before) - set(after), set())
        for rule_id, was in before.items():
            now = after[rule_id]
            self.assertEqual(now["valid_from"], was["valid_from"],
                             "a rule's opening moment moved")
            if now["valid_to"] != was["valid_to"]:
                # The ONLY admitted change, and it is the once-only close.
                self.assertIsNone(was["valid_to"], "a close was moved")
                self.assertEqual(now["valid_to"], self.boundary)

    def test_the_reversal_closed_the_scheduled_rule_and_opened_a_new_version(self):
        """What the second publish acted on, from the record's own account.

        The discriminating half is *which* rule it closed. A publish resolving
        as of now would have found rule A — still the rule in force, because
        the boundary has not arrived — and tried to move a close the first
        publish already wrote.
        """
        reversal = self._reverse()

        self.assertEqual(reversal.closed_rule_ids, [str(self.raised.pk)])
        self.assertEqual(len(reversal.opened_rule_ids), 1)
        reinstated = Rate.objects.get(pk=reversal.opened_rule_ids[0])
        self.assertEqual(reinstated.valid_from, self.boundary)
        self.assertIsNone(reinstated.valid_to)
        self.assertEqual(getattr(reinstated, THE_TERM), FIRST)
        # And the first publish's close is exactly where it was.
        self.rule.refresh_from_db()
        self.assertEqual(self.rule.valid_to, self.boundary)

    def test_the_reversed_rules_window_is_empty(self):
        self._reverse()

        self.raised.refresh_from_db()
        self.assertEqual(self.raised.valid_from, self.boundary)
        self.assertEqual(self.raised.valid_to, self.boundary)

    def test_the_empty_window_resolves_for_no_instant(self):
        """AC 3 — asserted on WHICH RULE answered, not on the amount.

        The amount cannot discriminate: the reversal puts the original price
        back, so a book where the reversal never happened answers the same
        number at all three instants. What separates the two is the rule the
        receipt names, and the reversed rule must never be it.
        """
        declares_a_markup(self.tenant)
        self._reverse()

        answered = [
            self._rule_that_answered(self.boundary - ONE_MICROSECOND),
            self._rule_that_answered(self.boundary),
            self._rule_that_answered(self.boundary + ONE_MICROSECOND),
        ]

        self.assertNotIn(str(self.raised.pk), answered)
        # And a rule DID answer at each of them, so "never it" is not "never
        # anything" — an empty window that swallowed the whole book would
        # satisfy the assertion above completely.
        self.assertEqual(len(answered), 3)
        self.assertTrue(all(answered))

    def test_no_row_is_reopened_and_the_database_is_what_refuses_it(self):
        """AC 2 — the write the rejected mechanism would have made.

        Driven through raw SQL, which is the door no service sits in front of:
        the claim is that reopening is impossible, not that the book service
        declines to do it.
        """
        self._reverse()
        self.rule.refresh_from_db()
        self.assertEqual(self.rule.valid_to, self.boundary)

        with self.assertRaises(IntegrityError) as refusal:
            with transaction.atomic():
                through_raw_sql(self.rule, valid_to=None)

        self.assertIn(SET_ONCE, str(refusal.exception))

    def _rule_that_answered(self, as_of):
        receipt = self.resolved(as_of)
        return receipt["provenance"]["price_rate_ids"].get(SCHEDULING_QUANTITY)


class TheHistoryIsCompleteTest(AForwardDatingBookMixin, TestCase):
    """AC 4 — *we scheduled a rise and reversed it*, read from the records.

    This is the second thing the ruling buys, and the one delete-and-reopen
    destroys outright: a mechanism that removes the rows removes the evidence
    that the decision was ever made. The assertions here read only
    `PricingBookPublish` rows, because "readable from the record alone" is the
    claim.
    """

    def setUp(self):
        super().setUp()
        self.boundary = timezone.now() + A_MONTH
        self.who_raised = member_actor(uuid4(), "raiser@example.com")
        self.who_reversed = member_actor(uuid4(), "reverser@example.com")

    def test_both_publishes_are_on_the_record_with_their_actors_and_instants(self):
        BookService.publish_declared(
            self.declare_at(self.boundary, SECOND), actor=self.who_raised)
        BookService.publish_declared(
            self.declare_at(self.boundary, FIRST), actor=self.who_reversed)

        history = list(PricingBookPublish.objects.filter(
            book=self.book).order_by("published_at"))

        self.assertEqual(len(history), 2)
        self.assertTrue(all(record.is_published for record in history))
        self.assertEqual([record.actor_display for record in history],
                         [self.who_raised.display, self.who_reversed.display])
        self.assertEqual([record.actor_id for record in history],
                         [self.who_raised.id, self.who_reversed.id])
        self.assertEqual([record.effective_at for record in history],
                         [self.boundary, self.boundary])
        # The decision itself: a rise, and then the amount it rose from.
        self.assertEqual(
            [record.changes[0][THE_TERM] for record in history],
            [SECOND, FIRST])

    def test_the_reversal_names_the_rule_the_rise_opened(self):
        """The two records chain, so the pair reads as one story.

        Without this the history is two unrelated publishes that happen to
        share an instant; with it, the second one says out loud that what it
        closed is what the first one opened.
        """
        rise = BookService.publish_declared(
            self.declare_at(self.boundary, SECOND), actor=self.who_raised)
        reversal = BookService.publish_declared(
            self.declare_at(self.boundary, FIRST), actor=self.who_reversed)

        self.assertEqual(reversal.closed_rule_ids, rise.opened_rule_ids)


class AReceiptWrittenBeforeTheScheduleSurvivesTest(AForwardDatingBookMixin,
                                                   TestCase):
    """AC 5 — the third thing the ruling buys.

    A receipt's provenance carries the id of the rule that priced the event. A
    cancellation that deleted and re-created rows would leave that id pointing
    at nothing; a further publish leaves it pointing at a row that still exists
    and is still closed at the same instant.

    ⚠ **THE RECEIPT IS PERSISTED AND READ BACK.** A resolution held in a local
    cannot be shown to have survived anything — a dictionary does not change
    because a row did, so asserting it has not is asserting a property of
    Python. It goes onto a posting through the model's own column constant and
    comes back through `refresh_from_db`.
    """

    def setUp(self):
        super().setUp()
        declares_a_markup(self.tenant)
        self.boundary = timezone.now() + A_MONTH
        self.posting = Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key=str(uuid4()),
            **{Posting.RECEIPT_COLUMN: self.resolved(timezone.now())})

    def test_the_pointed_at_rule_still_exists_and_is_still_closed_at_the_same_instant(self):
        self.publish_at(self.boundary, SECOND)
        self.publish_at(self.boundary, FIRST)

        self.posting.refresh_from_db()
        stored = getattr(self.posting, Posting.RECEIPT_COLUMN)
        priced_by = stored["provenance"]["price_rate_ids"][SCHEDULING_QUANTITY]

        self.assertEqual(priced_by, str(self.rule.pk))
        pointed_at = Rate.objects.get(pk=priced_by)
        self.assertEqual(pointed_at.valid_to, self.boundary)
        self.assertEqual(getattr(pointed_at, THE_TERM), FIRST)

    def test_the_receipt_still_reproduces_the_amount_it_was_written_for(self):
        """The pointer resolving is not the whole claim; the terms are.

        A row that survived with different terms would satisfy the case above
        and still make the receipt a lie about what the tenant was charged.
        """
        self.posting.refresh_from_db()
        charged = getattr(
            self.posting, Posting.RECEIPT_COLUMN)["totals"]["billed_cost_micros"]

        self.publish_at(self.boundary, SECOND)
        self.publish_at(self.boundary, FIRST)

        self.posting.refresh_from_db()
        stored = getattr(self.posting, Posting.RECEIPT_COLUMN)
        priced_by = stored["provenance"]["price_rate_ids"][SCHEDULING_QUANTITY]
        self.assertEqual(
            getattr(Rate.objects.get(pk=priced_by), THE_TERM), charged)


class ASeriesOfScheduledPublishesComposesTest(AForwardDatingBookMixin,
                                              TestCase):
    """AC 6 — ruling 14b, the one-pending-publish limit is gone.

    It was a v1 simplification whose reason was that two overlapping pending
    publishes need a rule for which wins where. That ambiguity was a property
    of **cancellation by deletion**, not of scheduling: once each publish
    closes what it supersedes as of its own effective instant, a series
    composes and nothing has to arbitrate.

    ⚠ **THE CASES BELOW ASSERT THAT MORE THAN ONE IS OUTSTANDING AT ONCE**,
    which is the thing the limit forbade. A series published one at a time,
    each after the last had taken effect, would compose under the limit too and
    would prove nothing about lifting it.
    """

    def setUp(self):
        super().setUp()
        self.t1 = timezone.now() + A_MONTH
        self.t2 = self.t1 + A_MONTH
        self.t3 = self.t2 + A_MONTH

    def test_three_boundaries_outstanding_at_once_compose_as_three_windows(self):
        self.publish_at(self.t1, SECOND)
        self.publish_at(self.t2, THIRD)
        self.publish_at(self.t3, FOURTH)

        # Every one of the three is still in the future, so all three are
        # pending simultaneously — the state the limit existed to forbid.
        self.assertLess(timezone.now(), self.t1)

        windows = [(rule.valid_from, rule.valid_to)
                   for rule in self.book.rates.order_by("valid_from")]
        self.assertEqual(windows[1:], [(self.t1, self.t2),
                                       (self.t2, self.t3),
                                       (self.t3, None)])

    def test_three_drafts_coexist_and_publish_in_order(self):
        """The other reading of "pending", and it has to work too.

        A draft writes no rule, so nothing about declaring three of them can
        collide. Publishing them in order is what turns three intentions into
        the three windows above.
        """
        drafts = [self.declare_at(self.t1, SECOND),
                  self.declare_at(self.t2, THIRD),
                  self.declare_at(self.t3, FOURTH)]

        self.assertEqual(self.book.rates.count(), 1)
        for draft in drafts:
            BookService.publish_declared(draft)

        self.assertEqual(
            [rule.valid_to for rule in self.book.rates.order_by("valid_from")],
            [self.t1, self.t2, self.t3, None])

    def test_the_windows_answer_in_order_across_the_series(self):
        declares_a_markup(self.tenant)
        self.publish_at(self.t1, SECOND)
        self.publish_at(self.t2, THIRD)
        self.publish_at(self.t3, FOURTH)

        self.assertEqual(
            [self.amount_at(timezone.now()),
             self.amount_at(self.t1),
             self.amount_at(self.t2),
             self.amount_at(self.t3)],
            [FIRST, SECOND, THIRD, FOURTH])


class APublishSitsAtOrAfterTheBooksLatestBoundaryTest(AForwardDatingBookMixin,
                                                      TestCase):
    """AC 7 — the constraint that replaces the limit.

    *At or after the latest already-scheduled boundary in that book.* Strictly
    after permits a series; **equal permits the reversal**, which is why the
    boundary case is not a rounding detail but the whole of ruling 3's
    legality; earlier is refused.
    """

    def setUp(self):
        super().setUp()
        self.t1 = timezone.now() + A_MONTH
        self.t2 = self.t1 + A_MONTH

    def test_an_empty_book_is_the_only_one_with_no_boundary_at_all(self):
        """⚠ THE `None` BRANCH, AND IT IS NARROWER THAN IT LOOKS.

        Every rule has an opening moment, so a book holding any rule at all
        has a boundary — reading this as *"the latest FUTURE boundary"* is the
        easy mistake, and it is the one that would put a clock in a rule whose
        whole point is that it has none. `None` means the book is empty.
        """
        self.assertIsNone(latest_scheduled_boundary(cost_book(self.tenant)))

    def test_a_books_first_rule_is_already_a_boundary_and_now_still_passes(self):
        """Vacuous IN EFFECT rather than absent, which is the honest wording.

        The book's only rule opened when it was created, so the floor is not
        `None` — it is that opening moment, behind the present. What makes the
        rule harmless here is that anything the clock floor admits is at or
        after it anyway, which is why the two compose rather than one standing
        in for the other.
        """
        self.assertEqual(latest_scheduled_boundary(self.book),
                         self.rule.valid_from)
        self.assertLess(self.rule.valid_from, timezone.now())

        published = self.publish_at(timezone.now(), SECOND)

        self.assertTrue(published.is_published)

    def test_the_latest_boundary_is_a_maximum_over_both_of_a_rules_moments(self):
        """⚠ ASKED WITH A RETIREMENT, BECAUSE A REPRICE CANNOT ANSWER IT.

        A reprice closes one rule and opens its replacement at the same value,
        so the furthest opening and the furthest close are the same instant and
        reading either column alone gives the right answer by accident. Only a
        rule **retired rather than replaced** separates them: it closes at an
        instant no rule opens at, and a boundary read from the openings alone
        would sit behind a close the book has already scheduled — admitting the
        very publish this refuses.
        """
        BookService.publish_declared(BookService.declare(
            self.book,
            [{"kind": CHANGE_RETIRE, "measurement_key": SCHEDULING_QUANTITY,
              "provider": SCHEDULING_PROVIDER,
              "event_type": SCHEDULING_EVENT_TYPE}],
            effective_at=self.t1))

        opened_at = [rule.valid_from for rule in self.book.rates.all()]
        self.assertNotIn(self.t1, opened_at)
        self.assertEqual(latest_scheduled_boundary(self.book), self.t1)

    def test_a_publish_at_the_latest_boundary_is_accepted(self):
        self.publish_at(self.t1, SECOND)

        reversal = self.publish_at(self.t1, FIRST)

        self.assertTrue(reversal.is_published)

    def test_a_publish_after_the_latest_boundary_is_accepted(self):
        self.publish_at(self.t1, SECOND)

        self.assertTrue(self.publish_at(self.t2, THIRD).is_published)

    def test_a_publish_before_the_latest_boundary_is_refused_by_its_own_code(self):
        """And the code is what is asserted, never the status.

        A 422 on the declaring route already means *you have not declared that
        grouping field* and *that rule is not there to reprice*. A tenant's
        automation has to be able to tell a date it can fix from a body it
        cannot, which is the distinguishability the two instant refusals beside
        this one were bought for.

        This case reaches the refusal that names the rule — the change touches
        the very rule already scheduled to close, which is the half the
        database refuses too. Its twin below reaches the book-wide floor.
        """
        self.publish_at(self.t2, SECOND)

        with self.assertRaises(Problem) as refusal:
            self.declare_at(self.t1, THIRD)

        self.assertEqual(refusal.exception.code, BEFORE_THE_BOUNDARY)
        self.assertIn("already scheduled to close", refusal.exception.detail)

    def test_a_publish_before_the_boundary_touching_another_rule_is_refused(self):
        """⚠ THE HALF ONLY THE SERVICE HOLDS, REACHED AT THE DECLARING ACT.

        The change here names a rule with no boundary of its own — nothing
        about it is scheduled, so carrying the publish out would move no close
        and the database would admit every statement it makes. What refuses it
        is the book-wide floor, and the reason is the one the planner exists
        for: this publish landing at `t1` changes what the publish already
        scheduled at `t2` will find in force, so the diff its tenant approved
        and the change that happens stop being the same change.

        This case and its twin below are the ONLY two that reach the floor:
        every other refusal in this class is the per-rule one wearing the same
        code, so without these two the floor could be deleted outright and the
        rest of the module would stay green. Measured, not assumed.
        """
        untouched = self._a_second_rule_with_no_boundary()
        self.publish_at(self.t2, SECOND)

        with self.assertRaises(Problem) as refusal:
            self._declare_on_the_second_rule(at=self.t1)

        self.assertEqual(refusal.exception.code, BEFORE_THE_BOUNDARY)
        # And it is refused for the book's sake rather than for this rule's:
        # the rule the change names is open-ended and closes at no instant.
        untouched.refresh_from_db()
        self.assertIsNone(untouched.valid_to)
        self.assertNotIn("already scheduled to close", refusal.exception.detail)

    def test_a_draft_on_another_rule_that_falls_behind_cannot_be_published(self):
        """The same half, reached at the PUBLISHING act instead.

        The draft was legal when it was declared: the book had nothing
        scheduled ahead. A publish then wrote a boundary past it, and the draft
        now states a change dated behind the book's own diary. The declaring
        check above cannot reach this — the book moved after it ran — which is
        why the floor lives in the planner both acts go through.
        """
        self._a_second_rule_with_no_boundary()
        stale = self._declare_on_the_second_rule(at=self.t1)
        self.publish_at(self.t2, SECOND)

        with self.assertRaises(Problem) as refusal:
            BookService.publish_declared(stale)

        self.assertEqual(refusal.exception.code, BEFORE_THE_BOUNDARY)
        self.assertNotIn("already scheduled to close", refusal.exception.detail)

    def _a_second_rule_with_no_boundary(self):
        """A rule in the same book that nothing has ever scheduled anything for.

        Both floor cases need one, because a change naming a rule that IS
        scheduled to close is caught by the per-rule refusal before the floor
        is reached.
        """
        return rate_in_default_book(
            self.tenant, provider=SCHEDULING_PROVIDER,
            event_type=SCHEDULING_EVENT_TYPE, measurement_key=ANOTHER_QUANTITY,
            rate_per_unit_micros=FIRST)

    def _declare_on_the_second_rule(self, *, at):
        return BookService.declare(
            self.book,
            [self.a_change(measurement_key=ANOTHER_QUANTITY,
                           **{THE_TERM: THIRD})],
            effective_at=at)

    def test_a_refused_publish_writes_no_draft(self):
        self.publish_at(self.t2, SECOND)
        before = PricingBookPublish.objects.count()

        with self.assertRaises(Problem):
            self.declare_at(self.t1, THIRD)

        self.assertEqual(PricingBookPublish.objects.count(), before)

    def test_a_draft_that_has_fallen_behind_a_boundary_cannot_be_published(self):
        """The case the check at declaring time cannot reach.

        A draft is legal when it is declared and the book moves under it — a
        second publish lands at a later instant. The draft is now dated behind
        the book's own diary, and publishing it is the interleave the ruling
        refuses. It is refused at the publishing act, by the same rule.
        """
        stale = self.declare_at(self.t1, THIRD)
        self.publish_at(self.t2, SECOND)

        with self.assertRaises(Problem) as refusal:
            BookService.publish_declared(stale)

        self.assertEqual(refusal.exception.code, BEFORE_THE_BOUNDARY)

    def test_the_rule_reads_the_book_and_never_a_clock(self):
        """What separates this floor from the clock floor beside it.

        `core.scheduling`'s floor reads the payload and the clock and no row;
        this one reads the book and no clock. Neither subsumes the other, and
        the day one starts reading what the other reads they stop being two
        rules — so the signature is pinned rather than described.
        """
        self.assertEqual(
            list(inspect.signature(latest_scheduled_boundary).parameters),
            ["book"])


class TheDatabaseRefusesTheEarlierCaseRegardlessTest(AForwardDatingBookMixin,
                                                     TestCase):
    """AC 8 — the guard is a restatement, not the only thing holding the rule.

    Ruling 14b refuses an earlier instant *because it is impossible anyway*:
    inserting a publish between two scheduled ones has to close a row a later
    publish has already closed. The service says so with a message; the
    database says so whatever the service does.

    ⚠ **AND THE SERVICE GUARD IS DELIBERATELY WIDER THAN THE DATABASE RULE.**
    The database refuses only the direct collision — a publish that touches the
    very rule already scheduled to close. The book-wide floor refuses the whole
    class, including a publish dated earlier that touches some other rule
    entirely, because such a publish silently changes what an already-scheduled
    one will do: the diff a tenant approved and the change that happens become
    different changes. Saying which half each mechanism holds is the point of
    this class.
    """

    def setUp(self):
        super().setUp()
        self.boundary = timezone.now() + A_MONTH
        self.earlier = timezone.now() + timedelta(days=1)
        self.publish_at(self.boundary, SECOND)
        self.rule.refresh_from_db()

    def test_the_write_the_publish_would_make_is_refused_at_the_database(self):
        """The statement itself, through every door, with no service in it.

        This is the write `publish_declared` would issue for a publish dated
        `earlier`: close, at its own instant, the rule its own instant finds —
        which is the rule the scheduled publish has already closed.
        """
        for name, door in DOORS:
            with self.subTest(door=name):
                with self.assertRaises(IntegrityError) as refusal:
                    with transaction.atomic():
                        door(self.rule, valid_to=self.earlier)
                self.assertIn(SET_ONCE, str(refusal.exception))
                self.rule.refresh_from_db()

    def test_the_close_the_scheduled_publish_wrote_is_where_it_was(self):
        """The refusals above changed nothing, which is the other half.

        A rule that had been left half-written by a refused statement would be
        a worse outcome than the interleave, and "something raised" is not
        evidence about the row.
        """
        self.assertEqual(self.rule.valid_to, self.boundary)


class ADiscardedDraftStillCostsNothingTest(AForwardDatingBookMixin, TestCase):
    """AC 10 — the cheap path, and where most changes of mind happen.

    A tenant who has not published yet pays nothing at all. That is the first
    of the four things the ruling buys, and it is why the draft state is worth
    having: the reversal above is the price of changing your mind *after*
    publishing, and this is the price of changing it before.
    """

    def test_discarding_writes_no_rule_and_closes_nothing(self):
        before = rules_snapshot(self.book)
        draft = self.declare_at(timezone.now() + A_MONTH, SECOND)

        BookService.discard(draft)

        self.assertEqual(rules_snapshot(self.book), before)
        self.assertEqual(PricingBookPublish.objects.filter(
            book=self.book).count(), 0)

    def test_declaring_a_draft_writes_no_rule_either(self):
        """Half of the case above is about DECLARING rather than discarding.

        If declaring wrote a rule, discarding would have something to take
        back — and taking one back is exactly the move the whole ruling exists
        because the database refuses.
        """
        before = rules_snapshot(self.book)

        self.declare_at(timezone.now() + A_MONTH, SECOND)

        self.assertEqual(rules_snapshot(self.book), before)
