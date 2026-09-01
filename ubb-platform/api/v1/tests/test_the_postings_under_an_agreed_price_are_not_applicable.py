"""What a piece of work sold at one agreed price does to the postings under it
(#418, spec §13 and §14).

**THE SINGLE MOST CONSEQUENTIAL RENDERING RULE IN THE SLICE, DRIVEN RATHER THAN
DESCRIBED.** The Event Type declaration carries the granularity, so a finer
declared quantity multiplies the postings a piece of work produces — sixty
per-minute postings under a fixed-price piece of work are sixty cost-only
postings, sixty receipts and sixty six-year retention obligations. Every one of
them is `not_applicable`, **never a zero**: sixty zeros read as sixty events that
earned nothing, while sixty `not_applicable`s say the revenue is somewhere else
and the reason beside each says where to look. For a fine-grained tenant this
becomes the most common pricing status in the system.

**AND THE TWO ECONOMIC STATES THIS SLICE MAKES REACHABLE, BOTH PRODUCED HERE.**
The registry has published `measurements_status.not_applicable` and
`pricing_receipt_subject_type.charge` since the commits that coined their sets,
deliberately and as complete sets, because *publishing two values now and a
third later is precisely what a CLOSED set may not do*. Neither is a ledger debt
and neither is seeded as one. What was missing was any mechanism that could
produce them: #417's discriminator plus the derivation answers the first, and
the receipt written for a Charge answers the second. This module is where both
stop being unreachable.

⚠ **THE DERIVED STATUS IS PROVED BY READING G10, NOT BY RESTATING IT.** *No
writable column for it exists* is a claim about every model in the app registry,
and `apps/platform/tests/test_model_naming.py` is the walk that makes it — so
the case below asks THAT gate rather than writing a second walk that agrees with
it on the day it is written.
"""
import uuid

import pytest

from api.v1.tests.test_a_delivered_unit_of_work_is_charged_once import (
    SOLD_PER_EVENT, SOLD_WHOLE, THE_AGREED_PRICE, ChargeTestBase,
)
from apps.metering.pricing.receipts import (
    PRICING_REGIME_KEY, pricing_method_of, pricing_mode_of, subject_type_of,
    validate_receipt,
)
from apps.metering.pricing.tests._helpers import (
    a_rule_that_prices_what_it_measures, priced_at,
)
from apps.metering.usage.measurements import measurements_status_for
from apps.metering.usage.models import Posting
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.tests.test_model_naming import (
    DERIVED_NEVER_STORED, columns_storing_a_derived_fact,
)
from apps.platform.work.models import Task
from core.vocabulary import (
    MEASUREMENTS_STATUS_NOT_APPLICABLE,
    NOT_APPLICABLE_REASON_FIXED_TASK_PRICING,
    NOT_APPLICABLE_REASON_TENANT_NOT_BILLING,
    PRICING_MODE_FIXED,
    PRICING_RECEIPT_SUBJECT_TYPE_CHARGE,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_NOT_APPLICABLE,
    USAGE_EVENT_KIND_TASK_CHARGE,
)

#: WHAT THE SUPPLIER WORK UNDER ONE OF THESE POSTINGS COST. Non-zero, because
#: the claim that survives is *cost-only*: a posting whose cost were zero too
#: would be satisfied by an engine that stopped resolving anything at all for
#: this regime.
A_SUPPLIER_COST = 250_000

#: WHAT ONE OF THESE POSTINGS WOULD BILL IF ITS PIECE OF WORK WERE PRICED PER
#: EVENT. Deliberately unlike both the supplier cost above and the agreed price,
#: so a case reading the wrong number reads as wrong rather than as equal to
#: something.
A_METERED_PRICE = 1_000_000

#: HOW MANY POSTINGS ONE PIECE OF WORK REPORTS under a fine-grained declaration.
#: Six rather than the spec's sixty: sixty is about what the rule COSTS a
#: tenant, and what a test can show is that the count is the DECLARATION'S
#: rather than one — which six proves and sixty only repeats.
POSTINGS_UNDER_ONE_PIECE_OF_WORK = 6


class AgreedPriceTestBase(ChargeTestBase):
    """#416's fixture, plus the readers this module needs on top of it."""

    def _a_metered_posting(self, task_id):
        """One metered posting under ``task_id``, carrying real supplier work.

        The supplier figure is STATED rather than resolved against a cost rule,
        because what every case here is about is the customer side: a cost that
        arrived through the caller is settled by the branch above the ladder and
        leaves the price side the only thing under test.
        """
        recorded = UsageService.record_usage(
            self.tenant, self.customer, f"call-{uuid.uuid4()}",
            event_type=SOLD_PER_EVENT, task_id=task_id,
            provider_cost_micros=A_SUPPLIER_COST,
            measurements=priced_at(A_METERED_PRICE))
        return Posting.objects.get(id=recorded["event_id"])

    def _projection_of(self, task_id):
        return Posting.objects.get(task_id=task_id,
                                   kind=USAGE_EVENT_KIND_TASK_CHARGE)

    def _receipt_of(self, posting):
        return getattr(posting, Posting.RECEIPT_COLUMN)


@pytest.mark.django_db
class TestAnAgreedPricesPostingsAreNotApplicableRatherThanZero(
        AgreedPriceTestBase):
    """AC 2 — the rule itself, and the shape of what it records."""

    def test_a_metered_posting_carries_no_customer_price_at_all(self):
        started = self._priced_work()

        posting = self._a_metered_posting(started)

        assert posting.pricing_status == PRICING_STATUS_NOT_APPLICABLE
        assert posting.billed_cost_micros is None

    def test_it_is_not_a_zero_and_the_database_is_what_says_so(self):
        """⚠ NULL AND 0 STAY DISTINGUISHABLE AT THE DATABASE, which is what
        `ck_posting_pricing_status_agrees_with_the_price` is for: a row cannot
        claim to be priced and carry no amount, and cannot claim to be unpriced
        and carry one. So *never zero* is not a convention here — a zero beside
        this status is a row the table refuses.
        """
        started = self._priced_work()

        posting = self._a_metered_posting(started)

        assert posting.billed_cost_micros != 0
        assert posting.billed_cost_micros is None

    def test_the_supplier_work_is_still_costed(self):
        """COST-ONLY, WHICH IS THE OTHER HALF OF THE RULE. The supplier work a
        piece of work sold at one agreed price really burns is really the
        tenant's COGS, and it is what the whole piece's margin is netted
        against — so the regime silences the price side and touches nothing on
        the cost side.
        """
        started = self._priced_work()

        posting = self._a_metered_posting(started)

        assert posting.provider_cost_micros == A_SUPPLIER_COST

    def test_work_priced_per_event_is_unaffected(self):
        """The discriminating half. A rule that answered `not_applicable` for
        every posting would satisfy every case above and be exactly as wrong as
        recording zeros."""
        a_rule_that_prices_what_it_measures(self.tenant,
                                            event_type=SOLD_PER_EVENT)
        started = self._start(task_type=SOLD_PER_EVENT)

        posting = self._a_metered_posting(started)

        assert posting.pricing_status == PRICING_STATUS_KNOWN
        assert posting.billed_cost_micros == A_METERED_PRICE
        assert posting.not_applicable_reason is None

    def test_an_event_under_no_piece_of_work_is_unaffected_either(self):
        """There is no whole piece of work for its revenue to sit on instead,
        so the ladder applies to it — which is what the recording path's own
        default regime says, driven rather than asserted about a constant."""
        a_rule_that_prices_what_it_measures(self.tenant,
                                            event_type=SOLD_PER_EVENT)

        posting = self._a_metered_posting(None)

        assert posting.pricing_status == PRICING_STATUS_KNOWN

    def test_the_reason_is_the_one_slice_4_coined_for_this_case(self):
        started = self._priced_work()

        posting = self._a_metered_posting(started)

        assert (posting.not_applicable_reason
                == NOT_APPLICABLE_REASON_FIXED_TASK_PRICING)

    def test_the_receipt_records_the_regime_and_the_reason_by_value(self):
        """⚠ THE RECORD AND THE COLUMN ARE ONE STATEMENT, NOT TWO. Every column
        the recording path writes is read back off the receipt it stores beside
        them (`costing_of`), so a posting and its receipt cannot come to
        disagree about why no price applied — and the regime rides by value
        because configuration can move and this record may not.
        """
        started = self._priced_work()

        posting = self._a_metered_posting(started)

        receipt = self._receipt_of(posting)
        assert receipt["pricing"]["status"] == PRICING_STATUS_NOT_APPLICABLE
        assert receipt["pricing"]["detail"][PRICING_REGIME_KEY] \
            == PRICING_MODE_FIXED
        assert (receipt["pricing"]["detail"]["not_applicable_reason"]
                == NOT_APPLICABLE_REASON_FIXED_TASK_PRICING)
        assert pricing_method_of(receipt) is None

    def test_no_price_rule_is_consulted_at_all(self):
        """⚠ THE LADDER IS NOT WALKED AND DISCARDED, IT IS NOT WALKED.

        A tenant can have perfectly good price rules for the very quantity this
        event reports — the regime is a fact about the SUBJECT, decided before
        any configuration is read. Recording which rules WOULD have matched
        would say the tenant's configuration produced this outcome when the
        regime did, and would hand a later reader ids to re-resolve from.
        """
        a_rule_that_prices_what_it_measures(self.tenant,
                                            event_type=SOLD_PER_EVENT)
        started = self._priced_work()

        posting = self._a_metered_posting(started)

        receipt = self._receipt_of(posting)
        assert posting.pricing_status == PRICING_STATUS_NOT_APPLICABLE
        assert receipt["provenance"]["price_rate_ids"] == {}
        assert receipt["pricing"]["detail"]["components"] == []

    def test_the_declared_granularity_decides_how_many_such_postings_there_are(
            self):
        """§14, driven. A finer declared unit multiplies `not_applicable`
        postings rather than zero-revenue ones — the count is the tenant's
        declaration's and the rule holds for every one of them.
        """
        started = self._priced_work()

        postings = [self._a_metered_posting(started)
                    for _ in range(POSTINGS_UNDER_ONE_PIECE_OF_WORK)]

        assert len(postings) == POSTINGS_UNDER_ONE_PIECE_OF_WORK
        assert {p.pricing_status for p in postings} == {
            PRICING_STATUS_NOT_APPLICABLE}
        assert {p.billed_cost_micros for p in postings} == {None}
        assert {p.not_applicable_reason for p in postings} == {
            NOT_APPLICABLE_REASON_FIXED_TASK_PRICING}

    def test_the_piece_of_work_counts_none_of_them_as_unpriced(self):
        """⚠ AN UNPRICED EVENT IS ONE UBB COULD NOT PRICE, AND THESE ARE NOT
        THAT. The rollup counts what it could not add so a reader can tell a
        complete total from a floor; counting a decision somebody made would
        mark every fixed-price piece of work permanently partial, and for a
        fine-grained tenant that is most of the system.
        """
        started = self._priced_work()
        for _ in range(POSTINGS_UNDER_ONE_PIECE_OF_WORK):
            self._a_metered_posting(started)

        work = Task.objects.get(id=started)

        assert work.unpriced_event_count == 0
        assert work.total_billed_cost_micros == 0

    def test_contained_work_takes_the_regime_of_the_piece_that_contains_it(
            self):
        """A subtask cannot be sold at one agreed price of its own — its
        containing piece of work is the whole-work altitude — and #415's
        `BEFORE INSERT` trigger refuses contained work whose regime differs. So
        an event recorded against the CHILD is under the parent's regime, and
        the recording path reads the leaf because reading the leaf reads both.
        """
        started = self._priced_work()
        contained = self._start(task_type=SOLD_WHOLE, parent_task_id=started,
                                idempotency_key=f"child-{uuid.uuid4()}")

        posting = self._a_metered_posting(contained)

        assert posting.pricing_status == PRICING_STATUS_NOT_APPLICABLE
        assert (posting.not_applicable_reason
                == NOT_APPLICABLE_REASON_FIXED_TASK_PRICING)


@pytest.mark.django_db
class TestPostureWinsWhenBothReasonsApply(AgreedPriceTestBase):
    """AC 3 — the tie-break, end to end, against the fact that falsified its
    original argument.

    Slice 4 recorded the ruling with the reason *"for a metering-only tenant no
    Charge is created anywhere"*. #416 made that false on purpose: such a tenant
    DOES get a Charge, because for them it is a recorded revenue and margin fact
    rather than a collection, and #417 projected it onto a posting. So the
    counter-example is now reachable, and the ruling has to stand on the
    narrower argument that survives — `fixed_task_pricing` says *the customer
    revenue for this event sits on the piece of work instead*, and for a tenant
    UBB does not bill there is no customer revenue anywhere to point at.

    This class builds exactly that tenant: the Charge exists, the bill never
    will, and the postings say which of those two facts is the reason. Its
    paired control is `test_the_reason_is_the_one_slice_4_coined_for_this_case`
    in the class above, which is the identical fixture in the BILLING posture
    and records the other value — a rule that ignored the posture would satisfy
    that one and fail here, and a rule that ignored the regime would satisfy
    neither. Built as two classes rather than one parametrized fixture so a
    reader never holds two postures in mind at once, which is the shape
    `test_an_agreed_price_is_pinned_before_the_work_runs.py` settled.
    """

    PRODUCTS = ["metering"]
    BILLING_MODE = None

    def test_the_posture_reason_is_recorded_and_not_the_regimes(self):
        started = self._priced_work()

        posting = self._a_metered_posting(started)

        assert posting.pricing_status == PRICING_STATUS_NOT_APPLICABLE
        assert (posting.not_applicable_reason
                == NOT_APPLICABLE_REASON_TENANT_NOT_BILLING)
        assert (posting.not_applicable_reason
                != NOT_APPLICABLE_REASON_FIXED_TASK_PRICING)

    def test_the_charge_the_more_specific_reason_would_point_at_does_exist(
            self):
        """⚠ THE HALF THAT MAKES THIS A TIE RATHER THAN A ONE-SIDED CASE.

        Without this the class proves only that a metering-only tenant records
        the posture reason, which a rule that never looked at the regime would
        also satisfy. What makes the ruling a RULING is that both facts are true
        at once and the more specific one is declined — so the Charge the other
        reason would send a reader to has to be shown to be there.
        """
        started = self._priced_work()
        self._a_metered_posting(started)

        self._close(started)

        assert self._charges_against(started).count() == 1
        assert self._projection_of(started).billed_cost_micros \
            == THE_AGREED_PRICE


@pytest.mark.django_db
class TestAChargePostingsMeasurementsStatusDerives(AgreedPriceTestBase):
    """AC 1 — `measurements_status.not_applicable` becomes producible.

    The status is DERIVED, never stored: all three answers are computable from
    facts the row already carries, so a column holding a fourth copy could only
    ever disagree with them. What makes the value reachable is #417's
    discriminator plus the derivation reading it — there is no new mechanism
    here, and that is the claim.
    """

    def test_a_charge_posting_reads_as_not_applicable(self):
        started = self._priced_work()

        self._close(started)

        assert measurements_status_for(self._projection_of(started)) \
            == MEASUREMENTS_STATUS_NOT_APPLICABLE

    def test_the_status_is_derived_and_no_column_stores_it(self):
        """⚠ ASKED THROUGH G10'S OWN ENTRY POINT, NOT THROUGH A COPY OF IT.

        *No writable column exists for this fact* is a claim about every column
        of every model in the app registry, which is the walk
        `apps/platform/tests/test_model_naming.py` already makes. A second walk
        here would be two encodings of one gate — the shape ADR-0006 §4 is
        itself about — and the copy is the one that goes quiet. The membership
        assertion beside it is the vacuity guard: a green answer from a gate
        that is not looking for this fact would say nothing at all.
        """
        assert "measurements_status" in DERIVED_NEVER_STORED
        assert columns_storing_a_derived_fact() == ""


@pytest.mark.django_db
class TestTheReceiptWhoseSubjectIsACharge(AgreedPriceTestBase):
    """AC 4 and AC 5 — `pricing_receipt_subject_type.charge` becomes producible.

    A receipt for a piece of work sold at one agreed price: no measurements, no
    supplier work, one pinned agreed price, the regime by value, and a NULL
    pricing method because the price was AGREED and not derived. Its validating
    consumer is the receipt module, which is what validates a subject at the one
    construction boundary — never the model that stores the record, which holds
    a `jsonb` column and has no opinion about what is in it.
    """

    def test_the_projection_carries_a_receipt_whose_subject_is_the_charge(self):
        started = self._priced_work()

        self._close(started)

        charge = self._charges_against(started).get()
        receipt = self._receipt_of(self._projection_of(started))
        assert subject_type_of(receipt) == PRICING_RECEIPT_SUBJECT_TYPE_CHARGE
        assert receipt["subject_id"] == str(charge.id)

    def test_the_subject_is_the_charge_and_not_the_row_it_is_stored_on(self):
        """⚠ THE RECORD STATES WHAT IT IS ABOUT; NOTHING INFERS IT FROM WHERE IT
        LIVES. Deriving the subject from the row a receipt is stored on would be
        a second authority able to disagree with the recorded one, which is what
        the typed subject exists to refuse — and this is the first record in the
        repository where the two answers differ.
        """
        started = self._priced_work()

        self._close(started)

        projection = self._projection_of(started)
        receipt = self._receipt_of(projection)
        assert receipt["subject_id"] != str(projection.id)

    def test_the_price_is_the_agreed_one_and_names_no_method(self):
        started = self._priced_work()

        self._close(started)

        receipt = self._receipt_of(self._projection_of(started))
        assert receipt["totals"]["billed_cost_micros"] == THE_AGREED_PRICE
        assert receipt["pricing"]["status"] == PRICING_STATUS_KNOWN
        assert pricing_method_of(receipt) is None

    def test_it_carries_the_regime_by_value(self):
        started = self._priced_work()

        self._close(started)

        assert pricing_mode_of(self._receipt_of(
            self._projection_of(started))) == PRICING_MODE_FIXED

    def test_it_records_no_supplier_work_and_no_measured_quantity(self):
        """The two absences that are what a Charge IS. The supplier work the
        piece of work really burned is on the metered postings beside this one,
        and a Charge priced no quantity: it is one whole piece of work at one
        number, which is why `measurements_status` answers *not applicable* for
        the same row.
        """
        started = self._priced_work()

        self._close(started)

        receipt = self._receipt_of(self._projection_of(started))
        assert receipt["totals"]["provider_cost_micros"] == 0
        assert receipt["costing"]["method"] is None
        assert receipt["costing"]["detail"] == {}
        assert receipt["pricing"]["detail"].get("components") is None

    def test_the_stored_record_is_a_valid_receipt(self):
        """⚠ ASSERTED ON WHAT IS IN THE COLUMN, not on what a constructor
        returned. A test that validates the value it just built proves the
        builder agrees with itself; reading the row back is the check that
        stays true the day somebody adds a second writer.
        """
        started = self._priced_work()

        self._close(started)

        validate_receipt(self._receipt_of(self._projection_of(started)))

    def test_the_line_and_the_book_version_ride_as_cross_references(self):
        """#139 §2.3's requirement, on the record: the amount is reproducible
        FROM THE RECORD rather than by re-resolving today's configuration, so
        the identity of the line that answered is a pointer and the number
        beside it is a value.
        """
        started = self._priced_work()

        self._close(started)

        charge = self._charges_against(started).get()
        receipt = self._receipt_of(self._projection_of(started))
        assert (receipt["provenance"]["agreed_price_line_id"]
                == str(charge.agreed_price_line_id))
        assert receipt["provenance"]["book_version"] == str(charge.book_version)
