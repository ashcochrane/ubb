"""A publish can be dated forward, and nothing runs at the effective instant
(#359).

A tenant who agrees a rise from the first of next month should not have to
remember to log in on the first of next month. Today they do — and if they are
an hour late, the events in between are priced wrongly, **permanently, on a
record with no re-invoice path behind it**.

**THE ROWS ARE WRITTEN WHEN THE PUBLISH LANDS, AND THE BOUNDARY IS A VALUE THE
RESOLVER READS.** That is what "no job, therefore no failure mode" means, and
this module is where it is a measurement rather than a comment. A late job would
price every event in the gap at the old rate; there is no job to be late.

**WHAT EACH CLASS BELOW IS FOR.**

* *Persisted immediately* — the rules exist, carrying a future boundary, before
  the instant arrives. Asserted as the actual rows and their two columns, plus
  the record's own account of what it opened and closed.
* *Nothing executes at the instant* — asserted on the **absence**, four ways: no
  task enqueued through either Celery funnel, no event written to the outbox, no
  periodic job in the beat schedule naming this package, and no signal receiver
  registered for either the rule or the record. A comment saying "no job" is not
  evidence.
* *The clock is the only thing that moves* — resolution before the boundary
  gives the old answer and at or after it gives the new one, with nothing having
  run in between. The three instants are read in one test, from one publish.
* *Predecessors are resolved at the publish's own instant* — the property that
  makes a **series** compose, and the one the next ticket depends on entirely.
  Resolving "as of now" would have each later publish act on the rule that is
  currently in force rather than on the one its own instant finds. Three
  boundaries, because the AC asks for three and because the third is where the
  book holds an unopened rule, an open one and a closed one at once.

**THE RETIRED WORDS THIS MODULE NEVER SPELLS.** The container's pointer and the
cost/price discriminator both carry ledger entries that are ceilings as well as
floors. Every book and rule here is built through `_helpers`, which carries
those two for its callers, and a book's rules are read through its reverse
relation rather than by filtering on the column that points at it. The
arithmetic-shape column has such an entry too and never comes up, because a
publish cannot move a rule's arithmetic shape and no fixture here states one.
"""

from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.db.models import signals
from django.test import TestCase
from django.utils import timezone

from apps.metering.pricing.models import PricingBookPublish, Rate
from apps.metering.pricing.services.book_service import BookService
from apps.metering.pricing.tests._helpers import (
    FIRST,
    FOURTH,
    SECOND,
    THE_TERM,
    THIRD,
    AForwardDatingBookMixin,
    declares_a_markup,
    rules_snapshot,
)
from apps.platform.events.models import OutboxEvent
from core.vocabulary import DECLARATION_STATUS_DRAFT

#: How far ahead the fixtures date a change. Comfortably inside the platform's
#: horizon, and far enough that no test could pass by the boundary having
#: quietly arrived while the test ran.
A_MONTH = timedelta(days=30)

#: The dotted prefix a periodic job would have to carry to be this package's.
THIS_PACKAGE = "apps.metering.pricing"

#: EVERY MODEL SIGNAL A WRITE TO ONE OF THESE MODELS RAISES. Named as a list so
#: that "nothing is scheduled" is a claim about the whole set rather than about
#: the two somebody remembered.
#:
#: Django declares ten; the four left out are named here so an omission cannot
#: read as deliberate. `class_prepared` fires once when a model class is defined
#: and never on a row. `pre_migrate`/`post_migrate` are the migration
#: lifecycle's. `m2m_changed` takes the THROUGH model as its sender, so asking
#: it about `Rate` would answer about nothing — and neither model here has a
#: many-to-many field for one to exist on.
EVERY_MODEL_SIGNAL_A_WRITE_RAISES = [
    signals.pre_init, signals.post_init,
    signals.pre_save, signals.post_save,
    signals.pre_delete, signals.post_delete,
]


class AFutureDatedPublishIsPersistedImmediatelyTest(
        AForwardDatingBookMixin, TestCase):
    """The rows exist before the instant arrives.

    This is what makes the whole design work: there is nothing left to happen
    at the boundary, so nothing can fail to happen.
    """

    def test_both_rules_are_on_disk_carrying_a_boundary_still_in_the_future(self):
        boundary = timezone.now() + A_MONTH

        record = self.publish_at(boundary, SECOND)

        self.assertLess(timezone.now(), boundary)
        outgoing = Rate.objects.get(pk=self.rule.pk)
        incoming = Rate.objects.get(pk=record.opened_rule_ids[0])
        self.assertEqual(outgoing.valid_to, boundary)
        self.assertEqual(incoming.valid_from, boundary)
        self.assertIsNone(incoming.valid_to)
        self.assertEqual(getattr(incoming, THE_TERM), SECOND)
        self.assertEqual(record.closed_rule_ids, [str(self.rule.pk)])

    def test_the_book_holds_both_versions_at_once_before_the_boundary(self):
        """Two rows for one rule, and only one of them answers today.

        A row that faithfully carries a future boundary is not the same thing as
        a row that is HONOURED at one, which is why the resolution cases below
        exist at all — but it is the precondition for them.
        """
        boundary = timezone.now() + A_MONTH

        self.publish_at(boundary, SECOND)

        self.assertEqual(self.book.rates.count(), 2)
        self.assertEqual(self.amount_at(timezone.now()), FIRST)

    def test_the_publish_record_is_published_rather_than_pending(self):
        """Nothing about the record stays open waiting for the instant.

        A record left in a state something would have to come back to is the
        same failure mode as a job, wearing the record's clothes.
        """
        boundary = timezone.now() + A_MONTH

        record = self.publish_at(boundary, SECOND)

        record.refresh_from_db()
        self.assertTrue(record.is_published)
        self.assertIsNotNone(record.published_at)
        self.assertLess(record.published_at, boundary)
        self.assertEqual(
            PricingBookPublish.objects.filter(
                book=self.book,
                declaration_status=DECLARATION_STATUS_DRAFT).count(), 0)


class NothingExecutesAtTheEffectiveInstantTest(
        AForwardDatingBookMixin, TestCase):
    """Asserted on the absence, four ways.

    ⚠ **THE POINT IS THAT THERE IS NOTHING TO BE LATE.** A job that priced the
    gap at the old rate would put a wrong number permanently on an authoritative
    record, so the design's whole claim is that no such job exists. A comment
    saying so is not evidence; each case below is the absence, measured.
    """

    def test_a_future_dated_publish_enqueues_no_task(self):
        """⚠ **RUN THROUGH THE ON-COMMIT CALLBACKS, BECAUSE THAT IS WHERE THIS
        REPOSITORY PUTS DEFERRED WORK.**

        `outbox.write_event` ends in `transaction.on_commit(...)`, and under a
        `TestCase` an on-commit callback never fires — so a publish that
        enqueued its boundary from inside one would reach neither mock, write no
        row, and leave this case green. `TestCase.captureOnCommitCallbacks`
        executes them, which is what makes the absence a claim about the whole
        publish rather than about its synchronous half. Found by
        `/code-review`'s SPEC axis, by no gate.
        """
        boundary = timezone.now() + A_MONTH

        with mock.patch("celery.app.task.Task.apply_async") as apply_async, \
                mock.patch("celery.app.base.Celery.send_task") as send_task:
            with self.captureOnCommitCallbacks(execute=True):
                self.publish_at(boundary, SECOND)

        # Both funnels: `.delay()` reaches `apply_async`, and a task addressed
        # by name reaches `send_task` without passing through it.
        self.assertEqual(apply_async.call_args_list, [])
        self.assertEqual(send_task.call_args_list, [])

    def test_a_future_dated_publish_writes_nothing_to_the_outbox(self):
        """The other way work gets deferred here, and it is the likelier one.

        The outbox is this repository's async default, so an event written now
        and handled later is exactly the shape a scheduled publish would take if
        anybody built one.
        """
        boundary = timezone.now() + A_MONTH
        before = OutboxEvent.objects.count()

        with self.captureOnCommitCallbacks(execute=True):
            self.publish_at(boundary, SECOND)

        self.assertEqual(OutboxEvent.objects.count(), before)

    def test_no_periodic_job_belongs_to_the_pricing_package(self):
        """The beat schedule, read rather than remembered.

        Adjacent task names are not evidence of a schedule and a schedule is not
        evidence of a task — so this reads the setting itself and asserts that
        nothing in it is this package's.
        """
        pricing_jobs = {
            name: entry["task"]
            for name, entry in settings.CELERY_BEAT_SCHEDULE.items()
            if entry["task"].startswith(THIS_PACKAGE)
        }

        self.assertEqual(pricing_jobs, {})

    def test_no_signal_receiver_is_registered_for_a_rule_or_a_record(self):
        """A deferred write hung on a model signal would be invisible to both
        checks above, so the third mechanism is asserted too — over every model
        signal a write to one of these models can raise, rather than over the
        two that come to mind. The four Django signals that are NOT in that set
        are named beside the constant.
        """
        for signal in EVERY_MODEL_SIGNAL_A_WRITE_RAISES:
            for model in (Rate, PricingBookPublish):
                with self.subTest(signal=signal, model=model.__name__):
                    receivers = signal._live_receivers(sender=model)
                    # Django 4.x returns a list; 5.x returns (sync, async).
                    if isinstance(receivers, tuple):
                        receivers = [r for group in receivers for r in group]
                    self.assertEqual(list(receivers), [])


class TheClockIsTheOnlyThingThatMovesTest(
        AForwardDatingBookMixin, TestCase):
    """Resolution before the boundary gives the old answer and at or after it
    gives the new one, **with no code having run in between**.

    The three reads happen one after another inside one test, from one publish,
    so the only difference between them is the instant asked about. That is the
    whole claim, and stating it as three separate tests would let a setUp run
    between them and quietly become the thing that changed.
    """

    def test_the_answer_changes_at_the_boundary_and_nothing_ran(self):
        declares_a_markup(self.tenant)
        boundary = timezone.now() + A_MONTH
        self.publish_at(boundary, SECOND)
        one_microsecond = timedelta(microseconds=1)

        before = self.amount_at(boundary - one_microsecond)
        at = self.amount_at(boundary)
        after = self.amount_at(boundary + one_microsecond)

        self.assertEqual([before, at, after], [FIRST, SECOND, SECOND])

    def test_the_rules_are_untouched_by_being_resolved_across_the_boundary(self):
        """Reading a price at an instant past the boundary writes nothing.

        If resolution were what applied a scheduled change — the shape a
        lazily-executed job takes — this is where it would show.
        """
        boundary = timezone.now() + A_MONTH
        record = self.publish_at(boundary, SECOND)
        before = rules_snapshot(self.book)
        published_at = record.published_at

        self.amount_at(boundary + timedelta(days=1))

        self.assertEqual(rules_snapshot(self.book), before)
        record.refresh_from_db()
        self.assertEqual(record.published_at, published_at)


class APublishResolvesItsPredecessorsAtItsOwnInstantTest(
        AForwardDatingBookMixin, TestCase):
    """A series of scheduled publishes composes, and that is why.

    ```
    A closes t1  ·  B runs [t1, t2)  ·  C runs [t2, t3)  ·  D runs [t3, ∞)
    ```

    **THREE BOUNDARIES, NOT TWO.** Two would already discriminate — the second
    publish must act on B while *as of now* the rule in force is still A,
    because t1 has not arrived — but the third is where the wrong reading gets
    its second chance: at t3 the book holds a rule that has not opened, one that
    has, and one already closed, and only the publish's own instant picks the
    right one out of the three. The next ticket depends on this entirely: it is
    the property that makes a series deterministic and therefore the property
    that makes lifting the one-pending limit safe.
    """

    def setUp(self):
        super().setUp()
        self.t1 = timezone.now() + A_MONTH
        self.t2 = self.t1 + A_MONTH
        self.t3 = self.t2 + A_MONTH

    def test_each_publish_closed_the_rule_its_own_instant_found(self):
        first = self.publish_at(self.t1, SECOND)
        opened_by_first = Rate.objects.get(pk=first.opened_rule_ids[0])

        second = self.publish_at(self.t2, THIRD)
        opened_by_second = Rate.objects.get(pk=second.opened_rule_ids[0])
        third = self.publish_at(self.t3, FOURTH)

        self.assertEqual(second.closed_rule_ids, [str(opened_by_first.pk)])
        self.assertEqual(third.closed_rule_ids, [str(opened_by_second.pk)])
        # And no earlier close moved. A publish that had acted on the rule
        # currently in force would have had to move one of these two.
        self.rule.refresh_from_db()
        opened_by_first.refresh_from_db()
        self.assertEqual(self.rule.valid_to, self.t1)
        self.assertEqual(opened_by_first.valid_to, self.t2)

    def test_the_four_windows_compose_without_gap_or_overlap(self):
        declares_a_markup(self.tenant)
        self.publish_at(self.t1, SECOND)
        self.publish_at(self.t2, THIRD)
        self.publish_at(self.t3, FOURTH)
        one_microsecond = timedelta(microseconds=1)

        answers = [
            self.amount_at(timezone.now()),
            self.amount_at(self.t1 - one_microsecond),
            self.amount_at(self.t1),
            self.amount_at(self.t2 - one_microsecond),
            self.amount_at(self.t2),
            self.amount_at(self.t3 - one_microsecond),
            self.amount_at(self.t3),
        ]

        self.assertEqual(
            answers,
            [FIRST, FIRST, SECOND, SECOND, THIRD, THIRD, FOURTH])

    def test_the_book_carries_four_versions_and_three_boundaries(self):
        """The diary itself, read from the rows.

        Four rows, each opening exactly where the last one closes, and only the
        newest left open-ended.
        """
        self.publish_at(self.t1, SECOND)
        self.publish_at(self.t2, THIRD)
        self.publish_at(self.t3, FOURTH)

        windows = [(rule.valid_from, rule.valid_to)
                   for rule in self.book.rates.order_by("valid_from")]

        opened_at = [start for start, _ in windows]
        closed_at = [end for _, end in windows]
        self.assertEqual(closed_at, [self.t1, self.t2, self.t3, None])
        # Each window opens exactly where the last one closes — asserted as the
        # equality rather than as two lists that happen to agree.
        self.assertEqual(opened_at[1:], closed_at[:-1])
