"""A Charge is written once and never edited, and the database is what says so
(#416, spec §11, ADR-0007 §2).

`api/v1/tests/test_a_delivered_unit_of_work_is_charged_once.py` proves WHEN a
charge arises, through the route a tenant actually calls. This module proves
what the row is afterwards, and it is deliberately at the DATABASE: a service
that declines to write is a message to its caller, while what ADR-0007 §2
requires is that the row cannot move whichever door the write came through —
because the doors that are not the route are the ones nobody is looking at. A
data migration, a management command, a shell session at three in the morning
with a customer on the phone.

Three claims:

* **EVERY ECONOMIC COLUMN IS FROZEN.** Whose money it is, what UBB charged, in
  which currency, against which line of which version of which book, and at
  which two instants, are facts about money that already moved. Twenty columns,
  all three doors, and each refusal names the column that moved rather than
  merely that something did.
* **A CORRECTION IS A COMPENSATING RECORD AND THE TRAIL IS READABLE.** The only
  correction there is, because the columns above cannot be rewritten: another
  row of this table naming the one it corrects, carrying the negation and its
  own reason. The original still says what UBB originally charged, which is the
  property an edit destroys.
* **EXACTLY ONE ORIGINAL CHARGE PER PIECE OF WORK, FOR ALL TIME.** The
  winning-transition guard in the close is what normally stops a second one;
  this is what holds when two closes race and both win their own read.

⚠ **THE RULE IS NOT ADDRESSED BY POSITION.** `pg_trigger` promises no order, so
this module names the rule it is about and asserts the table's rules as an exact
SET — which is what makes a second rule arriving something a person reads rather
than something an index silently starts pointing at (#352).
"""
from importlib import import_module

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.metering.pricing.models import Charge
from apps.metering.pricing.services.charge_service import compensate, derived_key
from apps.metering.pricing.tests._helpers import (
    DOORS, RefusalThroughEveryDoorMixin, a_price_for_whole_work,
    database_rules_guarding,
)
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.platform.work.models import Task
from core.transitions import FROZEN, columns_declared_into_defended_classes
from core.vocabulary import (
    PRICING_MODE_FIXED, TASK_STATUS_COMPLETED,
)

TABLE = Charge._meta.db_table

#: THE MIGRATION THAT INSTALLED THE RULE, IMPORTED FOR ITS COLUMN SET.
#:
#: Read off the migration rather than transcribed here, so that the declaration
#: on the model and the rule on the table are compared against ONE list instead
#: of against two copies of it that agree until somebody edits one. Deferred
#: into a call for the reason `_helpers.retired_kind_column` gives about a
#: migration import on a collection path: a squash deletes these files, and a
#: module-level import would turn that into a collection error across this
#: whole app rather than a failure in the two assertions that actually ask.
_RULE_MIGRATION = "0031_a_delivered_piece_of_work_is_charged_once"


def the_rules_column_set():
    return set(import_module(
        f"apps.metering.pricing.migrations.{_RULE_MIGRATION}").FROZEN_COLUMNS)

#: The rule this module's refusals belong to, addressed BY NAME.
TRANSITION_TRIGGER = "trg_charge_declared_transitions"

#: What the rule's message says about the class, so every refusal below can
#: assert the CLASS and the COLUMN together. Naming only one of the two is the
#: assertion that stops discriminating the day this table acquires a second
#: mechanism, which is what #352 paid for one app over.
FROZEN_IN_THE_MESSAGE = "declared frozen"

THE_AGREED_PRICE = 8_000_000
SOLD_WHOLE = "transcode"


class ChargeTestBase(TestCase):
    """One tenant, one piece of work carrying a pinned price, and a charge."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Charged",
                                            products=["metering"])
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")
        self.line = a_price_for_whole_work(
            self.tenant, task_type=SOLD_WHOLE, amount_micros=THE_AGREED_PRICE)

    def _delivered_work(self, **columns):
        return Task.objects.create(
            tenant=self.tenant, customer=self.customer,
            balance_snapshot_micros=0, task_type=SOLD_WHOLE,
            pricing_mode=PRICING_MODE_FIXED,
            agreed_price_micros=THE_AGREED_PRICE,
            agreed_price_line_id=self.line.id,
            agreed_price_book_version=self.line.pricing_book.version,
            status=TASK_STATUS_COMPLETED, completed_at=timezone.now(),
            **columns)

    def _charge(self, work=None, **columns):
        work = work or self._delivered_work()
        fields = dict(
            tenant=self.tenant, task=work, amount_micros=THE_AGREED_PRICE,
            currency="usd", agreed_price_line_id=self.line.id,
            book_version=self.line.pricing_book.version,
            resolved_at=work.created_at, charged_at=work.completed_at,
            idempotency_key=derived_key(work.id))
        fields.update(columns)
        return Charge.objects.create(**fields)


class EveryEconomicColumnOfAChargeIsFrozenTest(RefusalThroughEveryDoorMixin,
                                               ChargeTestBase):
    """AC 6 — the database refuses an update to any of them, through every door.

    ⚠ EVERY CASE ASSERTS THE COLUMN AS WELL AS THE CLASS, and here that is not
    the precaution it is on a single-column rule — it is the only thing making
    the assertions distinguishable at all. One rule holds twenty columns and
    answers with one class word for every one of them, so *the record is frozen*
    would be satisfied by the rule refusing any OTHER column of the same row.
    """

    def _refuses(self, charge, **columns):
        (column,) = columns
        return self.assert_every_door_refuses(
            charge,
            refusal=rf"{FROZEN_IN_THE_MESSAGE}.*\b{column}\b",
            **columns)

    def test_the_amount_cannot_be_rewritten(self):
        """The case the whole rule exists for. A charge whose number can be
        edited is a record of what somebody most recently believed rather than
        of what UBB charged."""
        self._refuses(self._charge(), amount_micros=1)

    def test_the_currency_cannot_be_rewritten(self):
        self._refuses(self._charge(), currency="eur")

    def test_the_piece_of_work_it_charges_for_cannot_be_rewritten(self):
        """Re-pointing a charge is how a customer ends up billed for somebody
        else's work with every amount still correct."""
        other = self._delivered_work()
        self._refuses(self._charge(), task_id=other.id)

    def test_the_tenant_whose_money_it_is_cannot_be_rewritten(self):
        """THE SAME DEFECT ONE LEVEL UP, and the first draft of this table froze
        the work and left this writable.

        Re-pointing the unit of work bills the wrong customer; re-pointing the
        TENANT moves the whole record into somebody else's books with every
        amount still correct, which is worse for the same reason it is harder to
        notice. ⚠ No gate could have found the omission: G19 asks whether every
        DECLARED column is defended and has nothing to say about a column that
        should have been declared and was not.
        """
        elsewhere = Tenant.objects.create(name="Elsewhere",
                                          products=["metering"])
        self._refuses(self._charge(), tenant_id=elsewhere.id)

    def test_the_line_that_answered_cannot_be_rewritten(self):
        self._refuses(self._charge(), agreed_price_line_id=self.tenant.id)

    def test_the_book_version_cannot_be_rewritten(self):
        self._refuses(self._charge(), book_version=99)

    def test_neither_instant_can_be_rewritten(self):
        """Both, because they answer different questions and a rule holding one
        would leave the other free: the charge instant decides which period the
        revenue lands in, and the resolution instant is what keeps margin exact
        across a boundary."""
        moved = timezone.now()
        self._refuses(self._charge(), charged_at=moved)
        self._refuses(self._charge(work=self._delivered_work()),
                      resolved_at=moved)

    def test_the_derived_key_cannot_be_rewritten(self):
        """The key is what makes a charge exactly-once downstream, so a writable
        one would let a second charge be minted by editing the first out of the
        way."""
        self._refuses(self._charge(), idempotency_key="task:something-else")

    def test_the_grouping_snapshot_cannot_be_rewritten(self):
        """All ten are declared and one is driven — the set is asserted whole in
        `TheDeclarationIsWhatTheDatabaseDefendsTest` below, which is the check
        that would notice a slot left out of the rule."""
        self._refuses(self._charge(), grouping_field_1="somewhere-else")

    def test_a_frozen_column_cannot_ride_along_with_a_permitted_change(self):
        """The interesting shape, because it is what an ordinary well-meant fix
        looks like: an operator writing a note and correcting the number in one
        statement. The rule judges the COLUMN, never the statement."""
        self.assert_every_door_refuses(
            self._charge(),
            refusal=rf"{FROZEN_IN_THE_MESSAGE}.*\bamount_micros\b",
            amount_micros=1, correction_note="fixing this")

    def test_the_note_beside_a_correction_still_moves(self):
        """THE CONTROL, and this class is worth nothing without it.

        Every case above asserts a refusal, which a rule refusing ALL updates to
        this table would satisfy completely — and that rule would be a different
        and much blunter thing than the one declared. `correction_note` is
        deliberately outside the frozen set: it is display text beside a
        correction rather than an economic fact, and freezing prose would refuse
        an operator the ability to finish a sentence.
        """
        original = self._charge()
        correction = compensate(original, note="raised too early")
        for name, door in DOORS:
            with self.subTest(door=name):
                door(correction, correction_note=f"reworded via {name}")
                correction.refresh_from_db()
                self.assertEqual(correction.correction_note,
                                 f"reworded via {name}")

    def test_the_rule_names_every_column_that_moved(self):
        """One statement moving two frozen columns is refused ONCE, naming
        both.

        A rule reporting only the first would leave an operator fixing one
        column at a time and meeting the same refusal again, and the message is
        the whole of what tells them what to do instead.
        """
        charge = self._charge()
        with self.assertRaises(IntegrityError) as refused:
            with transaction.atomic():
                Charge.objects.filter(pk=charge.pk).update(
                    amount_micros=1, currency="eur")
        self.assertIn("amount_micros", str(refused.exception))
        self.assertIn("currency", str(refused.exception))


class ACorrectionIsACompensatingRecordTest(ChargeTestBase):
    """AC 7 — an edit is refused and the compensating path leaves a trail."""

    def test_a_wrong_charge_is_corrected_by_a_record_naming_it(self):
        original = self._charge()

        correction = compensate(original, note="the customer was not delivered to")

        self.assertEqual(correction.compensates_id, original.id)
        self.assertEqual(correction.amount_micros, -THE_AGREED_PRICE)
        self.assertEqual(correction.task_id, original.task_id)
        self.assertEqual(correction.currency, original.currency)

    def test_the_original_still_says_what_ubb_originally_charged(self):
        """The property an edit destroys, asserted directly. This is what
        "leaves a trail" means and it is the whole argument for the compensating
        shape."""
        original = self._charge()

        compensate(original, note="raised in error")

        original.refresh_from_db()
        self.assertEqual(original.amount_micros, THE_AGREED_PRICE)
        self.assertEqual(original.correction_note, "")

    def test_the_trail_reads_as_a_net_of_nothing(self):
        """A reader nets the head against its corrections and needs to interpret
        nothing: a reversal takes the pair to zero."""
        original = self._charge()
        compensate(original, note="raised in error")

        trail = Charge.objects.filter(task_id=original.task_id)

        self.assertEqual(sum(row.amount_micros for row in trail), 0)
        self.assertEqual(trail.count(), 2)

    def test_a_corrected_number_is_a_second_compensating_record(self):
        """Re-stating a charge at a different number, which is the case a bare
        reversal does not cover on its own. Two corrections hang off one
        original, each with its own reason, and the net is the number that is
        now right."""
        original = self._charge()
        compensate(original, note="wrong price applied")
        restated = Charge.objects.create(
            tenant=self.tenant, task_id=original.task_id,
            amount_micros=3_000_000, currency=original.currency,
            agreed_price_line_id=original.agreed_price_line_id,
            book_version=original.book_version,
            resolved_at=original.resolved_at, charged_at=timezone.now(),
            idempotency_key=derived_key(original.task_id, correction=2),
            compensates=original, correction_note="restated at the agreed line")

        trail = Charge.objects.filter(task_id=original.task_id)

        self.assertEqual(sum(row.amount_micros for row in trail), 3_000_000)
        self.assertEqual(restated.compensates_id, original.id)

    def test_a_correction_of_a_correction_is_refused(self):
        """A trail has one head. Chaining would make *what is this charge now*
        a walk of unknown depth, and every reader would have to agree on how to
        do it."""
        original = self._charge()
        correction = compensate(original, note="raised in error")

        with self.assertRaisesRegex(ValueError, "the original charge"):
            compensate(correction, note="and again")

    def test_a_correction_says_why_and_an_original_has_nothing_to_say(self):
        """At the database, because the trail is only readable if each
        correction carries its own reason."""
        original = self._charge()
        with self.assertRaisesRegex(IntegrityError,
                                    "ck_charge_a_correction_says_why"):
            with transaction.atomic():
                Charge.objects.create(
                    tenant=self.tenant, task_id=original.task_id,
                    amount_micros=-THE_AGREED_PRICE, currency="usd",
                    agreed_price_line_id=self.line.id, book_version=1,
                    resolved_at=timezone.now(), charged_at=timezone.now(),
                    idempotency_key="task:silent-correction",
                    compensates=original)

    def test_an_original_charge_is_never_negative(self):
        """A charge that pays the customer to be delivered to is a sign error
        rather than a deal — and the exemption above it is what lets a
        correction be exactly that."""
        with self.assertRaisesRegex(IntegrityError,
                                    "ck_charge_an_original_is_not_negative"):
            with transaction.atomic():
                self._charge(amount_micros=-1)


class ExactlyOneOriginalChargePerPieceOfWorkTest(ChargeTestBase):
    """AC 1 at the database — what holds when two closes race."""

    def test_a_second_original_charge_is_a_database_error(self):
        charge = self._charge()

        with self.assertRaisesRegex(
                IntegrityError, "uq_charge_one_original_per_unit_of_work"):
            with transaction.atomic():
                self._charge(work=charge.task,
                             idempotency_key="task:a-second-attempt")

    def test_a_correction_is_not_refused_by_that_rule(self):
        """THE CONTROL. The uniqueness is PARTIAL on the correction pointer
        being null, and without this case a rule refusing every second row would
        satisfy the assertion above while making a correction unwritable."""
        charge = self._charge()

        correction = compensate(charge, note="raised in error")

        self.assertEqual(
            Charge.objects.filter(task_id=charge.task_id).count(), 2)
        self.assertIsNotNone(correction.pk)

    def test_the_derived_key_is_unique_within_the_tenant(self):
        """A DIFFERENT piece of work, carrying a key that is already claimed.

        The rule above stops the same work being charged twice; this stops two
        charges claiming one key, which is what a downstream money rail keys on.
        The work differs so that the refusal can only be this one.
        """
        charge = self._charge()
        other = self._delivered_work()

        with self.assertRaisesRegex(IntegrityError,
                                    "uq_charge_idempotency_key"):
            with transaction.atomic():
                self._charge(work=other,
                             idempotency_key=charge.idempotency_key)

    def test_two_tenants_never_collide(self):
        """Scoped to the tenant and not globally, matching every other key in
        this tree: two tenants' records cannot collide by construction, and a
        global rule would say they might."""
        charge = self._charge()
        elsewhere = Tenant.objects.create(name="Other", products=["metering"])
        their_customer = Customer.objects.create(tenant=elsewhere,
                                                 external_id="c1")
        their_line = a_price_for_whole_work(
            elsewhere, task_type=SOLD_WHOLE, amount_micros=THE_AGREED_PRICE)
        their_work = Task.objects.create(
            tenant=elsewhere, customer=their_customer,
            balance_snapshot_micros=0, task_type=SOLD_WHOLE,
            pricing_mode=PRICING_MODE_FIXED,
            agreed_price_micros=THE_AGREED_PRICE,
            agreed_price_line_id=their_line.id,
            agreed_price_book_version=their_line.pricing_book.version,
            status=TASK_STATUS_COMPLETED, completed_at=timezone.now())

        theirs = Charge.objects.create(
            tenant=elsewhere, task=their_work,
            amount_micros=THE_AGREED_PRICE, currency="usd",
            agreed_price_line_id=their_line.id,
            book_version=their_line.pricing_book.version,
            resolved_at=their_work.created_at,
            charged_at=their_work.completed_at,
            idempotency_key=charge.idempotency_key)

        self.assertEqual(theirs.idempotency_key, charge.idempotency_key)


class TheDeclarationIsWhatTheDatabaseDefendsTest(ChargeTestBase):
    """The two halves of ADR-0007 §2, and neither is worth anything alone.

    A rule with no declaration answers *what may happen to this?* nowhere; a
    declaration with no rule is the promise nothing keeps. The first is read off
    the model, the second off `pg_catalog`.
    """

    def test_every_economic_column_declares_frozen(self):
        declared = {column for name, column, transition_class
                    in columns_declared_into_defended_classes([Charge])
                    if transition_class == FROZEN}
        self.assertEqual(declared, the_rules_column_set())

    def test_the_rule_holds_exactly_what_the_model_declares(self):
        """⚠ THE SET IS COMPARED IN BOTH DIRECTIONS, WHICH THE GATE CANNOT DO.

        `test_transition_class_declarations.py` asks whether each declared column
        is NAMED somewhere in the rules on its table, and that is honest about
        being a search rather than a proof. What it cannot see is a column the
        RULE holds and the model never declared — a column frozen in fact and
        undocumented in the mapping every reader consults. Comparing the two
        sets says both things at once, and the refusals above are what say the
        rule actually holds.
        """
        self.assertEqual(set(Charge.transition_classes),
                         the_rules_column_set())

    def test_the_rule_is_installed_under_the_name_this_module_addresses(self):
        """The premise every assertion above rests on, asserted rather than
        assumed: a migration that ran is evidence a file executed, not that a
        rule is on the table. An exact SET rather than a membership test, so a
        second rule arriving is read by a person before the by-name addressing
        above quietly starts mattering.

        The catalogue query is `_helpers.database_rules_guarding`, which two
        modules on the rate's table already share -- a second copy of one
        catalogue query is two things that can drift apart while agreeing with
        each other, which is what `docs/conventions/testing.md:22` puts that
        module there to prevent.
        """
        self.assertEqual({name for name, _, _ in database_rules_guarding(TABLE)},
                         {TRANSITION_TRIGGER})

    def test_the_rule_never_enters_on_an_insert(self):
        """THE STATEMENT MASK, out of `pg_trigger` rather than out of the SQL
        this module could just as well re-read (`django-patterns.md`).

        Row-level and BEFORE the write: an `AFTER` trigger would refuse by
        rolling back work already done, and a statement-level one cannot see the
        old row at all, which is the only thing this rule is about.

        ⚠ AND THE `INSERT` BIT BEING OFF IS THE MIGRATION'S OWN COST ARGUMENT,
        ASSERTED RATHER THAN CLAIMED. That file says this rule carries no `WHEN`
        clause because nothing updates this table at all -- writing a charge is
        an INSERT and so is correcting one -- so every write this table actually
        takes must not enter the function. Without this case that is a sentence;
        with it, it is a fact about the catalogue.
        """
        (_, tgtype, _), = database_rules_guarding(TABLE)
        self.assertTrue(tgtype & (1 << 0), "not FOR EACH ROW")
        self.assertTrue(tgtype & (1 << 1), "not BEFORE")
        self.assertTrue(tgtype & (1 << 4), "does not fire on UPDATE")
        self.assertFalse(tgtype & (1 << 2), "fires on INSERT")
        self.assertFalse(tgtype & (1 << 3), "fires on DELETE")
