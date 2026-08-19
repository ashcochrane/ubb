"""The receipt outlives the measurements it explains (#350).

**THIS IS A PRECONDITION THAT WAS ALREADY SPENT.** The decision that authorised
splitting the measured quantities out of the posting closed with a condition:
if the receipt does not snapshot the quantities and rates it used, pruning is
unsafe and the split must not ship. The split shipped. So `main` has been live
on the strength of a promise the receipt had not kept, and these tests are what
keeps it.

**The premise is established rather than assumed.** Every test that asserts
something about a receipt after pruning goes through :func:`_prune`, which
deletes the measurement record and then asks the posting what it now holds — a
`pruned` measurements status and an empty bag — before handing the receipt
back. A test that asserted the receipt explains its amount without first
proving the detail was gone would pass just as happily against a receipt that
explains nothing, because the detail would still be there to explain it. The
tests that do NOT prune are the ones establishing a premise of their own: that
a record is unresolved before anything is removed, and that the two children a
retention job would meet are indistinguishable while both are still there.

**What is proved, and it is three different claims:**

1. **A calculated cost is reproducible from the receipt alone.** Each component
   carries the quantity, the rule's terms and the denominator by value, so the
   amount can be recomputed six years later with nothing else on disk. The
   arithmetic below is written out rather than taken from ``Rate.compute``,
   deliberately: the claim is that a reader who has only the record can arrive
   at the number, and a check that called the engine's own method would be
   asserting the engine agrees with itself. **Both arithmetic shapes are
   exercised**, because a rule that applies once regardless of quantity takes a
   different branch and a reproduction that only ever divided would be a claim
   about half the rules in the system.

2. **An unresolved record keeps its remediation inputs.** The quantities that
   matched no rule are in the receipt by value, so a recovery can price them
   once a rule exists — and every reader after the recovery has them with the
   measurement record gone. There were two ways to satisfy this and the ruling
   was that the receipt carries them, because an exemption is a second
   retention rule a pruning job must implement correctly forever and the day it
   does not, recovery stops working silently on exactly the records that most
   need fixing.

3. **No pruning exemption exists.** Nothing about an unresolved posting's
   measurement *record* makes it survive where a resolved one's would not: same
   columns, same null horizon, created by the same unconditional statement.
   What holds it is a fact about its **parent**, not a property of the row.

⚠ **THERE IS NO PRUNE JOB IN THIS REPOSITORY AND THIS COMMIT DOES NOT ADD ONE.**
`prunable_at` is a column with no clock behind it, and
`test_posting_measurement.py`'s own `TheHorizonHasNoClockBehindItTest` is what
stops one being started by accident. So "pruned" here means the state a prune
would leave, reached by removing the record — which is what any such job would
eventually issue — and claim 3 is a statement about what such a job would SEE.

⚠ **THE WHOLE-RECORD `DELETE` RULE HAS SINCE LANDED (#354), AND THIS IS WHAT IT
CHANGED HERE.** This module said the deletions below would stop being
unconditional and that the third class was where it would show up first. Both
happened. Every prune now goes through `release_and_prune`, because the
database refuses one before the record's horizon; and the classes whose posting
is unresolved settle the cost first, because it refuses one whose posting is
still waiting. **The rule itself is not proved here** — it is proved in
`test_a_measurement_is_pruned_only_when_it_may_be.py`, through three doors,
with its admitted move and with each condition's cause removed in turn. What
this module still asserts is its own subject: that the receipt keeps what a
reader needs once the detail is gone, and that nothing about an unresolved
record's own row exempts it.

**And the two mechanisms cover different windows, which is why neither replaces
the other.** The rule keeps the row while UBB is missing information; the
receipt keeps the inputs for everyone afterwards — including the readers of a
posting whose amount stayed absent by decision, whose record the rule releases
on time.

**Nothing here reconciles the two copies of a quantity.** The measurement record
holds what was reported and the receipt holds what was used to compute an
amount. They are not required to be equal, nothing ever compares them, and no
test below asserts they agree — see the note at the snapshot site in
`pricing/services/pricing_service.py`.

The receipt's column still carries the retired spelling of the concept and this
module never spells it: `Posting.RECEIPT_COLUMN` is what addresses it, so the
day the rename lands the module follows it rather than going quietly vacuous.
"""
import pytest
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.metering.pricing.models import Rate
from apps.metering.pricing.receipts import uncosted_quantity_keys
from apps.metering.pricing.tests._helpers import (
    cost_rate_in_default_book, declares_a_markup, rate_in_default_book)
from apps.metering.usage.measurements import measurements_status_for
from apps.metering.usage.models import Posting, PostingMeasurement
from apps.metering.usage.services.usage_service import UsageService
from apps.metering.usage.tests._helpers import (
    release_and_prune, release_the_horizon, settle_the_supplier_cost)
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from core.amount_status_pairs import SUPPLIER_COST
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_UNRESOLVED,
    MEASUREMENTS_STATUS_AVAILABLE,
    MEASUREMENTS_STATUS_PRUNED,
    PRICING_MODE_EVENT_PRICED,
    UNRESOLVED_REASON_COST_RATE_MISSING,
)

#: The column a refusal must NAME for this module to know WHICH of the child
#: rule's two conditions held (#354). Both refusals below are the status
#: condition's; asserting only `IntegrityError` would be satisfied just as well
#: by the horizon condition, which `release_the_horizon` has just cleared —
#: "something refused this" stops being evidence once a rule has two branches.
COSTING_STATUS_COLUMN = SUPPLIER_COST.status_column


def _tenant_and_customer():
    tenant = Tenant.objects.create(name="T")
    # ⚠ **THE PRUNE RULE READS THE PRICE STATUS TOO** (`usage/migrations/0041`),
    # so a tenant with no markup rung declared cannot prune anything: every
    # posting it records resolves to `unknown` (#356), which is one of the two
    # states the rule refuses to let a measurement leave. A rung of nothing —
    # the tenant charging what the call cost — is what these fixtures always
    # meant, and it settles the price so the module can go on being about the
    # COST half's rule.
    declares_a_markup(tenant)
    return tenant, Customer.objects.create(tenant=tenant, external_id="c1")


def _receipt_of(posting_id):
    return getattr(Posting.objects.get(id=posting_id), Posting.RECEIPT_COLUMN)


def _reproduce(component):
    """The amount a component claims, recomputed from the component alone.

    Written out rather than delegated to the rule's own method: what is being
    asserted is that everything the arithmetic needs is IN the record, and a
    reader six years from now has this and nothing else. Half-up on the
    denominator, which is the engine's rounding — a component that did not
    carry the denominator could not be rounded correctly at all.

    **BOTH SHAPES, BECAUSE THE RECORD CARRIES BOTH.** A rule that applies once
    regardless of quantity is its flat term and nothing else; one that charges
    per unit divides. A reproduction that only ever divided would answer a
    plausible wrong number for every rule of the first kind — and would happen
    to answer the right one for a rule whose per-unit term is zero, which is
    the sort of accident that reads as coverage.

    The shape is read through `Rate.STRUCTURE_COLUMN` rather than by naming the
    column, so this module never spells a word the ledger caps and follows the
    rename when it lands. The value literal is left alone deliberately: the
    canonical name for it is not yet the string in flight, which is
    `docs/conventions/coding-standards.md` §Vocabulary's own rule.
    """
    if component[Rate.STRUCTURE_COLUMN] == "flat":
        return component["fixed_micros"]
    quantity = component["units"]
    return ((quantity * component["rate_per_unit_micros"]
             + component["unit_quantity"] // 2)
            // component["unit_quantity"]) + component["fixed_micros"]


def _prune(posting_id):
    """Remove the measurement record behind a posting, and hand back its receipt.

    The receipt rather than the posting, because that is the whole subject: what
    survives is the record, and a caller reaching for it through the row would
    be spelling the column at every call site instead of once.

    The premise is established on the way through — available before, `pruned`
    after, and an empty bag — so a caller cannot assert the receipt explains an
    amount while the detail that explains it is still on disk.

    ⚠ **The deletion stopped being unconditional** (#354), which is the change
    this module's docstring said would show up here first. It now goes through
    `release_and_prune`, because the database refuses a `DELETE` before the
    record's horizon; and the caller must have taken its posting out of
    `unresolved` first, because it refuses one whose posting is still waiting.
    `_resolve_the_cost` below is how the classes that need that do it.
    """
    posting = Posting.objects.get(id=posting_id)
    assert measurements_status_for(posting) == MEASUREMENTS_STATUS_AVAILABLE
    release_and_prune(posting)

    posting = Posting.objects.get(id=posting_id)
    assert measurements_status_for(posting) == MEASUREMENTS_STATUS_PRUNED
    assert posting.measurements == {}
    return getattr(posting, Posting.RECEIPT_COLUMN)


def _resolve_the_cost(posting_id, micros):
    """Settle an unresolved supplier cost — the move a recovery run makes.

    A thin name over `settle_the_supplier_cost`, because every call site in this
    module holds a posting id rather than a posting. It exists because #354 made
    *resolving* the thing that releases a measurement record: before that a
    recovery and a prune were independent, and now the second waits on the
    first, which is the whole of what the rule says.
    """
    settle_the_supplier_cost(Posting.objects.get(id=posting_id), micros)


class ACalculatedCostIsReproducibleFromTheReceiptAloneTest(TestCase):
    """Obligation one: the quantities, the rules, the denominators, the amounts.

    Two quantities priced by two different rules, so a component that carried
    one rule's terms for both would be caught. The denominators differ for the
    same reason.
    """

    def setUp(self):
        self.tenant, self.customer = _tenant_and_customer()
        cost_rate_in_default_book(
            self.tenant, measurement_key="input_tokens",
            rate_per_unit_micros=3_000, unit_quantity=1_000)
        cost_rate_in_default_book(
            self.tenant, measurement_key="image_pixels",
            rate_per_unit_micros=17, unit_quantity=1_000_000,
            fixed_micros=250)
        self.result = UsageService.record_usage(
            self.tenant, self.customer, "r1", "k1",
            measurements={"input_tokens": 4_100, "image_pixels": 2_000_000})

    def test_every_component_reproduces_its_own_amount_after_the_prune(self):
        receipt = _prune(self.result["event_id"])

        components = receipt["costing"]["detail"]["components"]
        assert {line["measurement_key"] for line in components} == {
            "input_tokens", "image_pixels"}
        for line in components:
            assert line["micros"] == _reproduce(line), line

    def test_the_total_is_the_sum_of_components_the_receipt_still_holds(self):
        """The amount a tenant was charged, rebuilt from the record alone."""
        receipt = _prune(self.result["event_id"])

        assert receipt["costing"]["status"] == COSTING_STATUS_KNOWN
        assert receipt["costing"]["method"] == COSTING_METHOD_CALCULATED
        assert receipt["totals"]["provider_cost_micros"] == sum(
            _reproduce(line)
            for line in receipt["costing"]["detail"]["components"])

    def test_the_quantities_survive_the_record_they_were_reported_on(self):
        """The measured amounts are in the receipt, by value.

        Not compared with the measurement record — that record is gone, which
        is the point, and comparing them is the reconciliation this ticket
        refuses to build even where both are present.
        """
        receipt = _prune(self.result["event_id"])

        recorded = {line["measurement_key"]: line["units"]
                    for line in receipt["costing"]["detail"]["components"]}
        assert recorded == {"input_tokens": 4_100, "image_pixels": 2_000_000}

    def test_the_price_side_explains_itself_the_same_way(self):
        """One rule, asked of both sections.

        A price resolved against its own rule is reproducible on exactly the
        terms the cost side is, because it is the same shape built in the same
        place — and a component that only the cost branch filled would leave a
        priced event unexplainable.
        """
        rate_in_default_book(self.tenant, measurement_key="input_tokens",
                             rate_per_unit_micros=9_000, unit_quantity=1_000)
        result = UsageService.record_usage(
            self.tenant, self.customer, "r2", "k2",
            measurements={"input_tokens": 4_100})

        receipt = _prune(result["event_id"])

        components = receipt["pricing"]["detail"]["components"]
        assert components, "a priced event recorded no component at all"
        for line in components:
            assert line["micros"] == _reproduce(line), line
        assert receipt["totals"]["billed_cost_micros"] == sum(
            _reproduce(line) for line in components)

    def test_a_rule_that_applies_once_reproduces_too(self):
        """The other arithmetic shape, which takes the other branch.

        A rule that charges once regardless of quantity is its flat term, and
        the record has to say which shape it was or a reader cannot know
        whether to divide. ⚠ The per-unit formula would ANSWER CORRECTLY here
        by accident — this rule's per-unit term is zero, so dividing it gives
        nothing and the flat term survives the addition. That is exactly why
        the shape is asserted as well as the amount: the coincidence is what
        makes a one-branch reproduction look like coverage.
        """
        cost_rate_in_default_book(
            self.tenant, measurement_key="api_calls", fixed_micros=7_500,
            **{Rate.STRUCTURE_COLUMN: "flat"})
        result = UsageService.record_usage(
            self.tenant, self.customer, "r-flat", "k-flat",
            measurements={"api_calls": 9})

        receipt = _prune(result["event_id"])

        line, = receipt["costing"]["detail"]["components"]
        assert line[Rate.STRUCTURE_COLUMN] == "flat"
        assert line["micros"] == 7_500
        assert line["micros"] == _reproduce(line)

    def test_the_subjects_whole_job_pricing_regime_rides_by_value(self):
        """The third axis, recoverable without a live lookup.

        Carried and nothing more: the concept is declared already and the
        column it will one day be read from belongs to the slice that rebuilds
        the unit of work. What this asserts is that the receipt does not send a
        reader looking for it.
        """
        receipt = _prune(self.result["event_id"])

        assert receipt["pricing"]["detail"]["pricing_mode"] == (
            PRICING_MODE_EVENT_PRICED)


class AnUnresolvedRecordKeepsItsRemediationInputsTest(TestCase):
    """Obligation two: a recovery still works after the detail expires.

    One quantity has a rule and one does not, which is the mixed case the
    engine actually produces: the resolved line rides in the components and the
    unresolved one has to be somewhere, or a recovery has nothing to price.
    """

    def setUp(self):
        self.tenant, self.customer = _tenant_and_customer()
        cost_rate_in_default_book(
            self.tenant, measurement_key="input_tokens",
            rate_per_unit_micros=3_000, unit_quantity=1_000)
        self.result = UsageService.record_usage(
            self.tenant, self.customer, "r1", "k1",
            measurements={"input_tokens": 4_100, "image_pixels": 2_000_000})

    def _resolved_then_pruned(self):
        """The lifecycle the rule now imposes, in the order it imposes it.

        A run settles the cost using the inputs the receipt kept, which is what
        releases the record; the prune follows. Every assertion in this class
        is about what a reader has at the END of that sequence, which is the
        window the receipt exists for and the only one in which the row is
        gone.
        """
        _resolve_the_cost(self.result["event_id"], 12_300)
        return _prune(self.result["event_id"])

    def test_the_record_says_it_is_unresolved_and_why(self):
        """The premise, established before anything is pruned."""
        posting = Posting.objects.get(id=self.result["event_id"])

        assert posting.costing_status == COSTING_STATUS_UNRESOLVED
        assert posting.unresolved_reason == UNRESOLVED_REASON_COST_RATE_MISSING
        assert posting.provider_cost_micros is None

    def test_the_database_holds_the_record_until_the_posting_is_resolved(self):
        """⚠ The premise every test below now has to establish (#354).

        A recovery does not read the receipt because the row is gone — the row
        is still there while the posting is unresolved, and the database
        refuses to let it go. What the receipt is for is every reader AFTER the
        recovery: the moment the cost settles the record is prunable, and from
        then on the snapshot is the only copy of what was uncosted.

        So the obligation this class carries is unchanged and its reason is
        sharper. The two mechanisms cover different windows and neither
        replaces the other — which is exactly why the rule is a condition on
        the parent's status rather than an exemption living on this record.
        """
        posting = Posting.objects.get(id=self.result["event_id"])

        with pytest.raises(IntegrityError, match=COSTING_STATUS_COLUMN):
            with transaction.atomic():
                release_and_prune(posting)

        assert PostingMeasurement.objects.filter(posting=posting).exists()

    def test_the_uncosted_quantity_is_in_the_receipt_by_value(self):
        receipt = self._resolved_then_pruned()

        assert receipt["costing"]["detail"]["uncosted_quantities"] == {
            "image_pixels": 2_000_000}

    def test_the_reader_and_the_remediation_input_name_the_same_quantities(self):
        """The list a reader has always got, and the mapping beside it.

        **Asserted through the reader, not through the stored key.** The record
        holds both because one is what every existing caller asks for and the
        other is what a recovery needs, and they are derived from one another
        where they are written so they cannot disagree. Comparing the two
        stored keys would therefore be near enough to comparing a value with
        itself; comparing what a READER GETS with the remediation input is a
        claim about the seam that survives someone rewriting the writer — and
        it is what `uncosted_quantity_keys` exists to answer, which is where
        the three-way version dispatch lives.
        """
        detail = self._resolved_then_pruned()["costing"]["detail"]

        assert uncosted_quantity_keys(
            _receipt_of(self.result["event_id"])) == list(
                detail["uncosted_quantities"])

    def test_a_recovery_can_price_the_missing_line_from_the_receipt_alone(self):
        """The whole obligation, executed rather than described.

        The rule that was missing is written afterwards — which is what a
        remediation is — and the quantity it needs comes out of the receipt,
        with the measurement record gone. If the receipt held only a total and
        a pointer, this is the test that could not be written.

        **The live path is the oracle, not a number typed into this file.** An
        identical event recorded once the rule exists is what the recovery is
        trying to arrive at, so the answer taken from the receipt is compared
        against the answer the engine itself gives — which is the claim worth
        making, and which no hand-computed constant could make without being a
        second copy of the engine's arithmetic.
        """
        detail = self._resolved_then_pruned()["costing"]["detail"]

        late_rule = cost_rate_in_default_book(
            self.tenant, measurement_key="image_pixels",
            rate_per_unit_micros=17, unit_quantity=1_000_000, fixed_micros=250)
        live = UsageService.record_usage(
            self.tenant, self.customer, "r-late", "k-late",
            measurements={"image_pixels": 2_000_000})
        priced, = [line for line
                   in _receipt_of(live["event_id"])["costing"]["detail"][
                       "components"]
                   if line["measurement_key"] == "image_pixels"]

        quantity = detail["uncosted_quantities"]["image_pixels"]
        assert late_rule.compute(quantity) == priced["micros"]

    def test_the_line_that_did_resolve_is_still_explained(self):
        """A partly resolved cost is not a resolved cost, and the resolved part
        is still the floor a tenant is shown. It survives the prune too."""
        detail = self._resolved_then_pruned()["costing"]["detail"]

        resolved, = detail["components"]
        assert resolved["measurement_key"] == "input_tokens"
        assert resolved["micros"] == _reproduce(resolved)


class NoPruningExemptionExistsTest(TestCase):
    """The alternative that was rejected, asserted as absent.

    An unresolved record's measurement row is not special. It is created by the
    same unconditional statement and carries the same null horizon, so a
    retention job reading the row has nothing to tell the two apart by — which
    is the property that makes the receipt's snapshot the whole of the answer
    rather than half of it.

    ⚠ **THE DELETE STOPPED BEING UNCONDITIONAL, AND THIS IS THE CLASS THIS
    MODULE SAID IT WOULD SHOW UP IN FIRST** (#354). What changed is not the
    claim above but where the difference lives: **the record is identical and
    the condition is a fact about its PARENT.** That is the whole reason the
    rule had to be cross-table, and the reason it is not the exemption this
    class exists to deny — an exemption is something a pruning job has to
    implement correctly forever, and a database rule is something it cannot get
    wrong. `test_the_child_record_declares_no_column_that_could_exempt_it`
    below is unchanged and is where that distinction is held.

    The rule itself is proved in
    `test_a_measurement_is_pruned_only_when_it_may_be.py`, through three doors,
    with its admitted move and a mutation of each condition. What is asserted
    here is only what it means for this module's subject.
    """

    def setUp(self):
        self.tenant, self.customer = _tenant_and_customer()
        cost_rate_in_default_book(
            self.tenant, measurement_key="input_tokens",
            rate_per_unit_micros=3_000, unit_quantity=1_000)
        self.settled = UsageService.record_usage(
            self.tenant, self.customer, "r1", "k1",
            measurements={"input_tokens": 4_100})
        self.unsettled = UsageService.record_usage(
            self.tenant, self.customer, "r2", "k2",
            measurements={"image_pixels": 2_000_000})

    def _postings(self):
        settled = Posting.objects.get(id=self.settled["event_id"])
        unsettled = Posting.objects.get(id=self.unsettled["event_id"])
        assert settled.costing_status == COSTING_STATUS_KNOWN
        assert unsettled.costing_status == COSTING_STATUS_UNRESOLVED
        return settled, unsettled

    def test_both_postings_have_a_record_and_it_looks_the_same(self):
        settled, unsettled = self._postings()

        for posting in (settled, unsettled):
            record = PostingMeasurement.objects.get(posting=posting)
            assert record.prunable_at is None, posting.costing_status
            assert measurements_status_for(posting) == (
                MEASUREMENTS_STATUS_AVAILABLE)

    def test_the_child_record_declares_no_column_that_could_exempt_it(self):
        """The shape, so that an exemption cannot arrive as data either.

        Asserted as exact equality rather than as an absence of names somebody
        thought of: a column added here is a decision, and a check that listed
        the spellings it disliked would pass for the one nobody predicted.
        """
        columns = {field.name for field in PostingMeasurement._meta.fields}

        assert columns == {"id", "created_at", "updated_at", "posting",
                           "measurements", "recorded_at", "prunable_at"}

    def test_an_unresolved_records_payload_comes_away_exactly_as_a_settled_one(self):
        """Once resolved, and the two are then indistinguishable to the rule.

        ⚠ The `resolve` is the only thing this test gained (#354). Both records
        are released by the same statement and both come away in the same
        `DELETE`, which is the claim: there is no second rule for the one whose
        posting was once unresolved, and nothing about its history follows it.
        """
        settled, unsettled = self._postings()
        _resolve_the_cost(unsettled.id, 12_300)

        for posting in (settled, unsettled):
            release_the_horizon(posting)
        removed = PostingMeasurement.objects.filter(
            posting__in=(settled, unsettled)).delete()[0]

        assert removed == 2
        for posting in (settled, unsettled):
            posting.refresh_from_db()
            assert measurements_status_for(posting) == MEASUREMENTS_STATUS_PRUNED

    def test_while_it_is_unresolved_the_database_is_what_keeps_it(self):
        """The condition, and it is a fact about the POSTING.

        Two rows a retention job cannot tell apart, in one statement, and the
        one whose parent is still waiting is what refuses it — so a job that
        swept them together loses neither. That is the property an exemption
        living on this record could never have: it would have to be read, and a
        job that forgot to read it would take both.
        """
        settled, unsettled = self._postings()
        for posting in (settled, unsettled):
            release_the_horizon(posting)

        with pytest.raises(IntegrityError, match=COSTING_STATUS_COLUMN):
            with transaction.atomic():
                PostingMeasurement.objects.filter(
                    posting__in=(settled, unsettled)).delete()

        assert PostingMeasurement.objects.filter(
            posting__in=(settled, unsettled)).count() == 2

    def test_the_unresolved_posting_still_explains_itself_afterwards(self):
        """The reason no exemption is needed, in the same test class as the
        absence of one — the snapshot is what replaces it.

        The prune follows the resolution, which is the order #354 imposes; what
        the receipt still carries is what was uncosted *before* it, which is
        the only copy any reader has once the record is gone.
        """
        _, unsettled = self._postings()
        _resolve_the_cost(unsettled.id, 12_300)
        detail = _prune(unsettled.id)["costing"]["detail"]
        assert detail["uncosted_quantities"] == {"image_pixels": 2_000_000}
