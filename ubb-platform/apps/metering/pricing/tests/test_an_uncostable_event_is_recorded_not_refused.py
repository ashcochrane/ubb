"""A cost UBB cannot work out stops being a refusal (#320, spec §3.9).

Until this ticket, an event whose declared quantities matched no Cost Rate was
answered with a 422 and never recorded. **The supplier had already run the call
and already charged for it.** Refusing the record did not undo the spend — it
hid it, and the missing margin turned up a month later as a gap nobody could
account for.

What is worth testing here is the decision, not the plumbing: the compute spine
is the one place that says which of the three statuses a posting takes, and the
four answers below are the whole of what it may say. Each is asserted through
the real resolution path — a real tenant, real Cost Rates, real declarations —
because every one of them is a statement about what a tenant declared.

The settlement that completes an `unresolved` posting later is next door in
``test_cost_settlement.py``; the database's refusal of every illegal
combination is in ``usage/tests/test_an_unknown_cost_stops_being_zero.py``.
This module is about what is written in the first place.
"""
import pytest

from apps.metering.pricing.services.pricing_service import PricingService
from apps.metering.pricing.tests._helpers import (
    a_usage_event_subject,
    cost_rate_in_default_book,
    rate_in_default_book,
)
from apps.metering.usage.models import Posting
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import (
    EventType,
    Measurement,
    ReportedCostMapping,
)
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    AMOUNT_REPRESENTATION_MICROS,
    COSTING_METHOD_CALCULATED,
    COSTING_METHOD_REPORTED,
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_NOT_APPLICABLE,
    COSTING_STATUS_UNRESOLVED,
    SOURCE_KIND_CALLER_SUPPLIED,
    UNIT_TOKEN,
    UNRESOLVED_REASON_COST_RATE_MISSING,
    UNRESOLVED_REASON_REPORTED_COST_MISSING,
    PRICING_METHOD_MARGIN_OVER_COST,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_WAIVED,
)

EVENT_TYPE_KEY = "acme.embed"


def _tenant():
    return Tenant.objects.create(name="T", default_currency="usd")


def _customer(tenant, external_id="c1"):
    return Customer.objects.create(tenant=tenant, external_id=external_id)


def _declaration(tenant, *, costing_method=COSTING_METHOD_CALCULATED,
                 quantities=("prompt_tokens",), mapping=False):
    """An Event Type declared the way a tenant declares one.

    `quantities` and `mapping` are what make the *"carries no cost at all"*
    question answerable: an Event Type with neither has no axis a Cost Rate
    could name and nowhere a supplier figure could come from.
    """
    event_type = EventType.objects.create(
        tenant=tenant, key=EVENT_TYPE_KEY, costing_method=costing_method)
    for code in quantities:
        Measurement.objects.create(
            event_type=event_type, code=code, unit=UNIT_TOKEN,
            source_kind=SOURCE_KIND_CALLER_SUPPLIED)
    if mapping:
        ReportedCostMapping.objects.create(
            event_type=event_type, source_kind=SOURCE_KIND_CALLER_SUPPLIED,
            amount_representation=AMOUNT_REPRESENTATION_MICROS, currency="usd")
    return event_type


def _price(tenant, customer, **kwargs):
    kwargs.setdefault("selectors", {"event_type": EVENT_TYPE_KEY,
                                    "provider": "openai"})
    kwargs.setdefault("measurements", {"prompt_tokens": 1_000})
    kwargs.setdefault("caller_provider_cost", None)
    kwargs.setdefault("caller_billed", None)
    return PricingService.price(
        subject=a_usage_event_subject(),
        tenant=tenant, customer=customer, currency="usd", **kwargs)


def _cost_rate(tenant, *, measurement_key="prompt_tokens", micros=5_000):
    return cost_rate_in_default_book(
        tenant, provider="openai", event_type=EVENT_TYPE_KEY,
        measurement_key=measurement_key, rate_per_unit_micros=micros,
        unit_quantity=1_000)


@pytest.mark.django_db
class TestTheComputeSpineDecidesTheStatus:
    """The four answers, and nothing else decides any of them (spec §3.6)."""

    def test_a_quantity_that_matched_no_cost_rate_is_unresolved(self):
        """Case 1. No rate, so no amount — and the reason names the fix."""
        tenant = _tenant()
        _declaration(tenant)

        costing = _price(tenant, _customer(tenant))

        assert costing.costing_status == COSTING_STATUS_UNRESOLVED
        assert costing.unresolved_reason == UNRESOLVED_REASON_COST_RATE_MISSING
        assert costing.provider_cost_micros is None

    def test_the_unresolved_event_says_which_quantities_went_uncosted(self):
        """The status says THAT; this says WHICH. Neither replaces the other.

        Two quantities, one of them rated: the receipt names the one that was
        not, and does not name the one that was.
        """
        tenant = _tenant()
        _declaration(tenant, quantities=("prompt_tokens", "image_pixels"))
        _cost_rate(tenant, measurement_key="prompt_tokens")

        costing = _price(tenant, _customer(tenant),
                         measurements={"prompt_tokens": 1_000,
                                       "image_pixels": 40})

        assert costing.costing_status == COSTING_STATUS_UNRESOLVED
        assert (costing.pricing_receipt["costing"]["detail"]["uncosted_measurement_keys"]
                == ["image_pixels"])

    def test_a_partly_rated_event_records_no_amount_at_all(self):
        """A partly resolved cost is not a resolved cost.

        The rated half is real and stays on the receipt — that is where the
        floor lives — but storing it as *the* supplier cost is exactly the
        ambiguity the nullable column was introduced to remove: a number that
        cannot be told apart from a complete one.
        """
        tenant = _tenant()
        _declaration(tenant, quantities=("prompt_tokens", "image_pixels"))
        _cost_rate(tenant, measurement_key="prompt_tokens")

        costing = _price(tenant, _customer(tenant),
                         measurements={"prompt_tokens": 1_000,
                                       "image_pixels": 40})

        assert costing.provider_cost_micros is None
        # Over the WHOLE line list rather than a cost-only filter: no price rate
        # exists in this fixture, so every line is a cost line, and asserting on
        # all of them catches a line that arrived with the wrong key instead of
        # filtering it silently away.
        rated = costing.pricing_receipt["costing"]["detail"]["components"]
        assert [line["measurement_key"] for line in rated] == ["prompt_tokens"]
        assert rated[0]["micros"] == 5_000

    def test_a_reported_event_with_no_supplier_figure_is_unresolved(self):
        """Case 2. The declaration says a supplier reports the cost; none came."""
        tenant = _tenant()
        _declaration(tenant, costing_method=COSTING_METHOD_REPORTED,
                     quantities=(), mapping=True)

        costing = _price(tenant, _customer(tenant), measurements={})

        assert costing.costing_status == COSTING_STATUS_UNRESOLVED
        assert (costing.unresolved_reason
                == UNRESOLVED_REASON_REPORTED_COST_MISSING)
        assert costing.provider_cost_micros is None

    def test_a_reported_event_whose_figure_arrived_is_known(self):
        """The positive control for the case above: the same declaration, and
        the one thing that was missing supplied, resolves."""
        tenant = _tenant()
        _declaration(tenant, costing_method=COSTING_METHOD_REPORTED,
                     quantities=(), mapping=True)

        costing = _price(tenant, _customer(tenant), measurements={},
                         caller_provider_cost=7_500)

        assert costing.costing_status == COSTING_STATUS_KNOWN
        assert costing.provider_cost_micros == 7_500
        assert costing.unresolved_reason is None

    def test_a_reported_declaration_with_no_mapping_is_still_not_free(self):
        """A `reported` Event Type carries a cost whether or not the mapping
        that says where to read it has been declared yet.

        Both halves of *"no rate axis and no cost mapping"* are absent here, so
        a rule that only counted them would call this call free. The method
        itself is the declaration that a supplier charges for it, and a mapping
        nobody has written yet is an outstanding task.
        """
        tenant = _tenant()
        _declaration(tenant, costing_method=COSTING_METHOD_REPORTED,
                     quantities=(), mapping=False)

        costing = _price(tenant, _customer(tenant), measurements={})

        assert costing.costing_status == COSTING_STATUS_UNRESOLVED
        assert (costing.unresolved_reason
                == UNRESOLVED_REASON_REPORTED_COST_MISSING)

    def test_an_event_type_that_carries_no_cost_is_not_applicable(self):
        """Case 3. A design decision, and never presented as an outstanding task."""
        tenant = _tenant()
        _declaration(tenant, quantities=())

        costing = _price(tenant, _customer(tenant), measurements={})

        assert costing.costing_status == COSTING_STATUS_NOT_APPLICABLE
        assert costing.provider_cost_micros is None
        assert costing.unresolved_reason is None

    def test_a_call_that_genuinely_cost_nothing_is_a_resolved_zero(self):
        """Case 4. `known` and zero — free and unknown are never the same row."""
        tenant = _tenant()
        _declaration(tenant)
        _cost_rate(tenant, micros=0)

        costing = _price(tenant, _customer(tenant))

        assert costing.costing_status == COSTING_STATUS_KNOWN
        assert costing.provider_cost_micros == 0
        assert costing.unresolved_reason is None

    def test_a_fully_rated_event_is_known(self):
        tenant = _tenant()
        _declaration(tenant)
        _cost_rate(tenant)

        costing = _price(tenant, _customer(tenant))

        assert costing.costing_status == COSTING_STATUS_KNOWN
        assert costing.provider_cost_micros == 5_000
        assert costing.unresolved_reason is None

    def test_an_undeclared_event_type_costs_the_way_it_always_did(self):
        """The registry is opt-in, and absence is not a declaration.

        Nothing in this repository has ever required an Event Type to be
        declared before recording against it. Reading that absence as *"carries
        no cost"* would report a design decision nobody made, on every posting
        of every tenant who has not adopted the registry.
        """
        tenant = _tenant()
        _cost_rate(tenant)

        costing = _price(tenant, _customer(tenant))

        assert costing.costing_status == COSTING_STATUS_KNOWN
        assert costing.provider_cost_micros == 5_000

    def test_a_caller_supplied_figure_needs_no_declaration_at_all(self):
        """WHERE such a figure may be supplied is #324's refusal, which sits at
        the recording edge and has already run by the time the spine is called.
        Costing one that arrived is this ticket's, and it costs without a
        lookup — the spine asks no declaration on this branch, which is what
        makes the edge's own query the only one either path pays for."""
        tenant = _tenant()

        costing = _price(tenant, _customer(tenant), caller_provider_cost=900)

        assert costing.costing_status == COSTING_STATUS_KNOWN
        assert costing.provider_cost_micros == 900


@pytest.mark.django_db
class TestAMarginOverACostUbbNeverLearnedIsWaived:
    """⚠ **THE FLOOR IS GONE, AND ITS OWN COMMENT SAID THIS WOULD HAPPEN.**

    This class used to be `TestNoBilledFigureMovesOnTheRateCardBranch`, and what
    it pinned was `markup(0)` — a price built on a basis UBB had not resolved,
    reported as settled because there was no other answer the record could hold.
    Its docstring said whether such a price may call itself settled is
    `pricing_status`, "which is slice 4's word"; #351 built the column and
    #356's resolver is what writes it.

    **THE ANSWER IS `waived`** (#147 §7.3). The rung cannot compute: a margin is
    a percentage of what the call cost, and UBB does not know what the call
    cost. Holding an uncomputable charge open forever is how a receivable nobody
    will ever collect sits in a tenant's figures, so it is recorded as a loss
    rather than queued — and `waived` is never a candidate for a recovery run.

    ⚠ **THE COST SIDE OF THIS CLASS HAS NOT MOVED AT ALL**, which is what bounds
    the change: the supplier cost is `unresolved` with the same reason and the
    same resolved lines in the receipt, and the settlement that completes it
    still works. What moved is the price built on top of it.
    """

    def test_a_partly_costed_event_waives_its_margin_rather_than_flooring_it(self):
        tenant = _tenant()
        from apps.metering.pricing.models import TenantMarkup
        TenantMarkup.objects.create(tenant=tenant,
                                    markup_percentage_micros=20_000_000)
        _declaration(tenant, quantities=("prompt_tokens", "image_pixels"))
        _cost_rate(tenant, measurement_key="prompt_tokens")

        costing = _price(tenant, _customer(tenant),
                         measurements={"prompt_tokens": 1_000,
                                       "image_pixels": 40})

        assert costing.provider_cost_micros is None
        assert costing.billed_cost_micros is None
        assert costing.pricing_status == PRICING_STATUS_WAIVED
        # NO METHOD BESIDE NO AMOUNT. A method is how an amount was arrived at,
        # so naming one where nothing was derived would be the record claiming
        # an arithmetic it never did.
        assert costing.pricing_receipt["pricing"]["method"] is None

    def test_a_price_rate_is_unaffected_by_an_unresolved_cost(self):
        tenant = _tenant()
        _declaration(tenant)
        # A PRICE rate — the helper's default, and left unnamed here because the
        # word that names the other kind is retired and capped (see
        # `_helpers.cost_rate_in_default_book`).
        rate_in_default_book(
            tenant, provider="openai",
            event_type=EVENT_TYPE_KEY, measurement_key="prompt_tokens",
            rate_per_unit_micros=11_000, unit_quantity=1_000)

        costing = _price(tenant, _customer(tenant))

        assert costing.costing_status == COSTING_STATUS_UNRESOLVED
        assert costing.billed_cost_micros == 11_000


@pytest.mark.django_db
class TestADeclarationThatDisownsCostRatesDisownsThemAsAMarkupBasis:
    """The declaration decides what the markup rung may be taken over.

    THE RULING: an Event Type declared `reported` or declared with no cost at
    all is the tenant saying its Cost Rates are not this Event Type's cost —
    `reported` means the supplier's own figure is — so marking up a basis the
    declaration disowns would invent a number, in the flattering direction,
    which is the whole failure this slice deletes.

    ⚠ **THE TWO DECLARATIONS PART COMPANY AT THE PRICE, AND THAT IS THE POINT
    OF THE STATUSES (#356).** `reported` with no figure yet is UBB not KNOWING
    the cost, so a margin over it is `waived`. No cost at all is the tenant
    saying there IS none, so the basis is genuinely zero and a margin over it
    settles — at the uplift, which is `known` and may well be nothing. Both
    null the supplier cost and the two look identical in the amount; the status
    is the only thing that tells them apart, which is why the rung branches on
    it rather than on the figure.
    """

    def _marked_up_tenant(self):
        from apps.metering.pricing.models import TenantMarkup
        tenant = _tenant()
        TenantMarkup.objects.create(tenant=tenant,
                                    markup_percentage_micros=20_000_000)
        return tenant

    def test_a_reported_declaration_waives_rather_than_marking_up_its_cost_rates(self):
        tenant = self._marked_up_tenant()
        _declaration(tenant, costing_method=COSTING_METHOD_REPORTED,
                     quantities=("prompt_tokens",), mapping=True)
        _cost_rate(tenant)

        costing = _price(tenant, _customer(tenant))

        assert costing.costing_status == COSTING_STATUS_UNRESOLVED
        assert costing.billed_cost_micros is None
        assert costing.pricing_status == PRICING_STATUS_WAIVED
        assert costing.pricing_receipt["pricing"]["method"] is None

    def test_the_same_event_bills_over_the_figure_once_it_arrives(self):
        """The positive control, and what makes the waiver above a verdict about
        the information rather than about the event: one input arrives and the
        price appears."""
        tenant = self._marked_up_tenant()
        _declaration(tenant, costing_method=COSTING_METHOD_REPORTED,
                     quantities=("prompt_tokens",), mapping=True)
        _cost_rate(tenant)

        costing = _price(tenant, _customer(tenant), caller_provider_cost=5_000)

        assert costing.costing_status == COSTING_STATUS_KNOWN
        assert costing.billed_cost_micros == 6_000

    def test_an_event_type_carrying_no_cost_settles_its_margin_over_zero(self):
        """The believed basis, and the half that is NOT waived.

        A declaration of no cost is information UBB has, not information it
        lacks: the basis is zero because the tenant said so. So the rung settles
        rather than waiving, and the price it settles at is the uplift — here
        nothing, which is a decided figure and not an absent one.
        """
        tenant = self._marked_up_tenant()
        _declaration(tenant, quantities=())
        _cost_rate(tenant)

        costing = _price(tenant, _customer(tenant))

        assert costing.costing_status == COSTING_STATUS_NOT_APPLICABLE
        assert costing.billed_cost_micros == 0
        assert costing.pricing_status == PRICING_STATUS_KNOWN
        assert (costing.pricing_receipt["pricing"]["method"]
                == PRICING_METHOD_MARGIN_OVER_COST)

    def test_a_price_rate_still_charges_whatever_the_declaration_says(self):
        """The half that is NOT at stake: a declared price is a declared price.

        A tenant who states what they charge is unaffected by any of this, which
        is what bounds the change above to one population.
        """
        tenant = self._marked_up_tenant()
        _declaration(tenant, costing_method=COSTING_METHOD_REPORTED,
                     quantities=("prompt_tokens",), mapping=True)
        rate_in_default_book(
            tenant, provider="openai", event_type=EVENT_TYPE_KEY,
            measurement_key="prompt_tokens",
            rate_per_unit_micros=11_000, unit_quantity=1_000)

        costing = _price(tenant, _customer(tenant))

        assert costing.costing_status == COSTING_STATUS_UNRESOLVED
        assert costing.billed_cost_micros == 11_000


@pytest.mark.django_db
class TestTheRecordingCallStopsRefusing:
    """The tenant-visible half: the call that used to be answered 422.

    ``record_usage`` is the whole recording path — pricing, the posting, the
    measurement child, the outbox emission — so a posting that comes back from
    here is one that survived every writer between the spine and the database,
    including the `CHECK` that refuses an illegal combination of amount, status
    and reason.
    """

    def test_the_event_is_recorded_rather_than_refused(self):
        tenant = _tenant()
        customer = _customer(tenant)
        _declaration(tenant)

        result = UsageService.record_usage(
            tenant, customer, "req-1", "idem-1",
            event_type=EVENT_TYPE_KEY, provider="openai",
            measurements={"prompt_tokens": 1_000})

        posting = Posting.objects.get(id=result["event_id"])
        assert posting.costing_status == COSTING_STATUS_UNRESOLVED
        assert posting.unresolved_reason == UNRESOLVED_REASON_COST_RATE_MISSING
        assert posting.provider_cost_micros is None

    def test_the_response_says_the_cost_is_not_settled(self):
        """At the moment the gap is created, not at period close."""
        tenant = _tenant()
        customer = _customer(tenant)
        _declaration(tenant)

        result = UsageService.record_usage(
            tenant, customer, "req-2", "idem-2",
            event_type=EVENT_TYPE_KEY, provider="openai",
            measurements={"prompt_tokens": 1_000})

        assert result["costing_status"] == COSTING_STATUS_UNRESOLVED
        assert result["provider_cost_micros"] is None

    def test_a_quantity_naming_a_declaration_nobody_made_is_not_fully_costed(self):
        """#265's second hand-forward, and it is payable rather than buildable.

        The hand-forward asked that an event whose quantity names a declaration
        nobody made be "marked not fully costed", and could not be paid when it
        was written because no such mark existed — the costing status is this
        slice's. It exists now, and the mark it asks for is the one this posting
        already takes, so what this ticket owes is the assertion rather than a
        second mechanism.

        WHY THE FIXTURE IS BUILT THIS WAY. The declared quantity is fully rated,
        so the posting's `unresolved` cannot be read as "the rates are
        incomplete" — everything the tenant declared has a rate, and the only
        thing left is a name their declaration does not mention. The neighbours
        above cover an unrated quantity that IS declared; this covers the other
        one, and the pair is what makes the status about the name.

        ⚠ THE OTHER SIDE OF THIS FACT IS NOT CROSS-CHECKED, AND #329 CLAIMED IT
        WAS. Quarantine answers the same question for the period close — which
        events a month cannot account for — but its own test asserts only its
        query, creates no posting and never reads a costing status, so a drift
        here leaves it green. The two definitions cannot be compared until
        something on the recording path holds a name, and nothing does yet; the
        quarantine test module records what closes it.
        """
        tenant = _tenant()
        customer = _customer(tenant)
        _declaration(tenant, quantities=("prompt_tokens",))
        _cost_rate(tenant, measurement_key="prompt_tokens")

        result = UsageService.record_usage(
            tenant, customer, "req-5", "idem-5",
            event_type=EVENT_TYPE_KEY, provider="openai",
            measurements={"prompt_tokens": 1_000, "reasoning_tokens": 40})

        posting = Posting.objects.get(id=result["event_id"])
        assert posting.costing_status == COSTING_STATUS_UNRESOLVED
        assert posting.provider_cost_micros is None
        assert posting.unresolved_reason == UNRESOLVED_REASON_COST_RATE_MISSING

        # THE CONTROL, IN THE SAME FIXTURE, and it is what makes the assertion
        # above evidence rather than a coincidence: the identical event without
        # the undeclared name resolves. A rate that had silently failed to
        # resolve would leave the first event unresolved for a reason that has
        # nothing to do with what this test claims, and this is the assertion
        # that fails when it does.
        control = UsageService.record_usage(
            tenant, customer, "req-6", "idem-6",
            event_type=EVENT_TYPE_KEY, provider="openai",
            measurements={"prompt_tokens": 1_000})

        assert control["costing_status"] == COSTING_STATUS_KNOWN
        assert control["provider_cost_micros"] == 5_000

    def test_a_replay_answers_what_the_original_recording_concluded(self):
        tenant = _tenant()
        customer = _customer(tenant)
        _declaration(tenant)
        first = UsageService.record_usage(
            tenant, customer, "req-3", "idem-3",
            event_type=EVENT_TYPE_KEY, provider="openai",
            measurements={"prompt_tokens": 1_000})

        replay = UsageService.record_usage(
            tenant, customer, "req-3", "idem-3",
            event_type=EVENT_TYPE_KEY, provider="openai",
            measurements={"prompt_tokens": 1_000})

        assert replay["event_id"] == first["event_id"]
        assert replay["costing_status"] == COSTING_STATUS_UNRESOLVED
        assert replay["provider_cost_micros"] is None

    def test_a_task_total_excludes_an_unresolved_cost_rather_than_zeroing_it(self):
        """The unit total accumulates the KNOWN part and is a floor.

        WHAT THIS CAN AND CANNOT SHOW, stated because the difference is not
        obvious: it catches an accumulator that adds the `None` this ticket now
        produces, which would 500 on the very call it was meant to record. It
        does NOT distinguish skipping an unresolved cost from adding a zero for
        it — both leave this total at 0, and nothing on the unit tells them
        apart until #328 adds the counter that says how many rows were excluded.
        That is the ticket to strengthen this assertion in, and claiming the
        stronger reading here would be claiming a mutation nothing kills.
        """
        from apps.platform.work.models import Task
        tenant = _tenant()
        customer = _customer(tenant)
        _declaration(tenant, quantities=("prompt_tokens", "image_pixels"))
        _cost_rate(tenant, measurement_key="prompt_tokens")
        task = Task.objects.create(tenant=tenant, customer=customer,
                                   balance_snapshot_micros=0)

        UsageService.record_usage(
            tenant, customer, "req-4", "idem-4", task_id=task.id,
            event_type=EVENT_TYPE_KEY, provider="openai",
            measurements={"prompt_tokens": 1_000, "image_pixels": 40})

        task.refresh_from_db()
        assert task.total_provider_cost_micros == 0
        assert task.event_count == 1


class TestTheRefusalIsGoneFromTheTree:
    """The exception class and the wire code it produced are retired.

    Asserted as absence, which is only evidence because the same names were
    importable and published on the commit before this one — every reference in
    this module's own imports would have failed to resolve otherwise.
    """

    def test_the_pricing_service_exports_no_error_class(self):
        import apps.metering.pricing.services.pricing_service as spine

        assert not hasattr(spine, "PricingError")

    def test_the_wire_code_is_retired_from_the_registry(self):
        from core.problems import PROBLEMS, VERDICTS

        assert "pricing_error" not in PROBLEMS
        assert "pricing_error" not in VERDICTS["ingest_rejections"]
