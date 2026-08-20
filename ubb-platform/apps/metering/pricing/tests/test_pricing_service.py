"""Rate resolution and the arithmetic over it.

**The refusal cases left with the refusal (#320).** Four tests here existed to
assert that an event naming a quantity with no Cost Rate was *rejected*, under a
tenant flag this ticket stopped reading on the compute path; a fifth asserted
the permissive half of the same branch. (The flag outlived #320 by one
commit — its last read was the admission gate in
`billing/gating/services/risk_service.py`, which refused to START a
COGS-limited unit without it, and #321 deleted the column, that gate and its
refusal code together.) The event is now recorded with its cost said to be
unresolved, and
what it says is asserted where the decision is made —
``test_an_uncostable_event_is_recorded_not_refused.py``, which covers all four
statuses through the same resolution path. They are not relaxed here into
weaker versions of themselves: the guarantee they defended (an uncosted quantity
is never silently a zero) is *stronger* now and is held by a `CHECK` constraint
as well as by that module.
"""
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import Rate
from apps.metering.pricing.services.pricing_service import PricingService
from apps.metering.pricing.tests._helpers import (
    a_usage_event_subject, declares_a_markup, rate_in_default_book)
from apps.platform.event_types.tests._helpers import declares_a_quantity
from core.vocabulary import (
    COSTING_METHOD_REPORTED,
    PRICING_METHOD_DIRECT_EVENT_PRICE,
    PRICING_METHOD_MARGIN_OVER_COST,
    PRICING_STATUS_UNKNOWN,
    RATE_STRUCTURE_FIXED_COMPONENT,
)


@pytest.mark.django_db
class TestPricing:
    def _t(self, **kw):
        return Tenant.objects.create(name="T", **kw)

    def test_caller_cost_wins_then_markup(self):
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        declares_a_markup(t, percentage_micros=20_000_000)
        costing = PricingService.price(
            subject=a_usage_event_subject(),
            tenant=t, customer=c, selectors={"event_type": "chat", "provider": "openai"},
            measurements=None, currency="usd",
            caller_provider_cost=1_000_000)
        assert costing.provider_cost_micros == 1_000_000
        assert costing.billed_cost_micros == 1_200_000
        assert (costing.pricing_receipt["pricing"]["method"]
                == PRICING_METHOD_MARGIN_OVER_COST)

    def test_cost_card_computes_provider_when_no_caller_cost(self):
        """The cost resolves; the price does not, because nothing prices it.

        ⚠ This used to assert `billed == 5` — the customer charged exactly what
        the call cost, because a tenant with no markup configured got the basis
        back unchanged. That is a price nobody stated, and #356 answers it
        `unknown` instead: there is no rule and no markup rung, so UBB does not
        have the information. The cost half is what this test is about and it
        has not moved.
        """
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        rate_in_default_book(t, card_type="cost", provider="openai", event_type="chat",
            measurement_key="input_tokens", grouping_field_1="gpt-4",
            rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        costing = PricingService.price(
            subject=a_usage_event_subject(),
            tenant=t, customer=c,
            selectors={"event_type": "chat", "provider": "openai",
                       "grouping_field_1": "gpt-4"},
            measurements={"input_tokens": 1000}, currency="usd",
            caller_provider_cost=None)
        assert costing.provider_cost_micros == 5
        assert costing.billed_cost_micros is None
        assert costing.pricing_status == PRICING_STATUS_UNKNOWN

    def test_price_card_charges_on_different_metric(self):
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        rate_in_default_book(t, card_type="cost", provider="openai", event_type="chat",
            measurement_key="input_tokens", rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        # Seats needs a COST declaration of its own now, and a rate of zero is
        # one: a quantity that matched no Cost Rate makes the whole posting
        # unresolved (#320), which would have turned this into a test of that
        # instead of of price resolution. "This supplier charges nothing for
        # seats" is a thing a tenant can now say, and saying it is the point.
        rate_in_default_book(t, card_type="cost", provider="openai", event_type="chat",
            measurement_key="seats", rate_structure=RATE_STRUCTURE_FIXED_COMPONENT, fixed_micros=0)
        rate_in_default_book(t, card_type="price", provider="openai", event_type="chat",
            measurement_key="seats", rate_structure=RATE_STRUCTURE_FIXED_COMPONENT, fixed_micros=9_000_000)
        costing = PricingService.price(
            subject=a_usage_event_subject(),
            tenant=t, customer=c, selectors={"event_type": "chat", "provider": "openai"},
            measurements={"input_tokens": 1000, "seats": 3}, currency="usd",
            caller_provider_cost=None)
        assert costing.provider_cost_micros == 5
        assert costing.billed_cost_micros == 9_000_000
        assert (costing.pricing_receipt["pricing"]["method"]
                == PRICING_METHOD_DIRECT_EVENT_PRICE)

    def test_most_specific_dimension_wins_and_wildcard_fallback(self):
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        rate_in_default_book(t, card_type="cost", provider="o", event_type="e",
            measurement_key="tok", rate_per_unit_micros=1_000, unit_quantity=1_000_000)
        rate_in_default_book(t, card_type="cost", provider="o", event_type="e",
            measurement_key="tok", grouping_field_1="gpt-4", rate_per_unit_micros=9_000, unit_quantity=1_000_000)
        costing = PricingService.price(
            subject=a_usage_event_subject(),
            tenant=t, customer=c,
            selectors={"event_type": "e", "provider": "o",
                       "grouping_field_1": "gpt-4"},
            measurements={"tok": 1_000_000}, currency="usd",
            caller_provider_cost=None)
        assert costing.provider_cost_micros == 9_000
        fallback = PricingService.price(
            subject=a_usage_event_subject(),
            tenant=t, customer=c,
            selectors={"event_type": "e", "provider": "o",
                       "grouping_field_1": "other"},
            measurements={"tok": 1_000_000}, currency="usd",
            caller_provider_cost=None)
        assert fallback.provider_cost_micros == 1_000

    def test_a_caller_supplied_cost_answers_for_a_quantity_with_no_rate(self):
        """The caller-cost branch is asked first and resolves on its own.

        This used to be the flag-off half of a pair whose flag-on half raised.
        The refusal is gone; what it was really pinning — that a supplied figure
        is the answer and does not go looking for rates to confirm it — is not.
        """
        t = self._t()
        c = Customer.objects.create(tenant=t, external_id="c3")
        costing = PricingService.price(
            subject=a_usage_event_subject(),
            tenant=t, customer=c, selectors={"event_type": "e", "provider": "o"},
            measurements={"unmatched_metric": 100}, currency="usd",
            caller_provider_cost=500,
        )
        assert costing.provider_cost_micros == 500
        assert (costing.pricing_receipt["costing"]["method"]
                == COSTING_METHOD_REPORTED)

    def test_nothing_to_price_is_a_marker_event(self):
        """No quantities and no caller cost → accepted at zero.

        F2.4's second strict-mode refusal rejected an event that declared a
        nameless magnitude with no quantity name to resolve a rate card against.
        #272 deleted the magnitude, so the refusal became unexpressible rather
        than relaxed; the event with nothing to price was always accepted and
        still is. It reads as a resolved zero because nothing about it went
        uncosted — there was nothing to cost.
        """
        t = self._t()
        c = Customer.objects.create(tenant=t, external_id="c5")
        costing = PricingService.price(
            subject=a_usage_event_subject(),
            tenant=t, customer=c,
            selectors={"event_type": "e", "provider": "o"},
            measurements=None, currency="usd",
            caller_provider_cost=None)
        assert costing.provider_cost_micros == 0

    def test_caller_cost_with_no_metrics_is_accepted(self):
        # Cost is explicitly known and there is nothing else to resolve.
        t = self._t()
        c = Customer.objects.create(tenant=t, external_id="c7")
        costing = PricingService.price(
            subject=a_usage_event_subject(),
            tenant=t, customer=c, selectors={"event_type": "e", "provider": "o"},
            measurements=None, currency="usd",
            caller_provider_cost=123)
        assert costing.provider_cost_micros == 123
        assert (costing.pricing_receipt["costing"]["method"]
                == COSTING_METHOD_REPORTED)


def test_unassigned_customer_uses_provider_default_book(db):
    from apps.metering.pricing.models import Rate, RateCard
    from apps.metering.pricing.services.pricing_service import PricingService
    from apps.platform.tenants.models import Tenant
    from apps.platform.customers.models import Customer
    from django.utils import timezone
    t = Tenant.objects.create(name="T", default_currency="usd")
    c = Customer.objects.create(tenant=t, external_id="c1")
    book = RateCard.objects.create(tenant=t, card_type="price", provider_key="gemini",
                                   currency="usd", key="gemini", is_default=True)
    r = Rate.objects.create(tenant=t, provider="gemini",
                            measurement=declares_a_quantity(t, "input_tokens"), currency="usd",
                            rate_per_unit_micros=10, rate_card=book)
    got = PricingService._resolve_card(t, c, "price", {"provider": "gemini"},
                                       "input_tokens", "usd", timezone.now())
    assert got is not None and got.id == r.id


def test_assigned_book_wins_then_falls_back_to_default(db):
    from apps.metering.pricing.models import Rate, RateCard, RateCardAssignment
    from apps.metering.pricing.services.pricing_service import PricingService
    from apps.platform.tenants.models import Tenant
    from apps.platform.customers.models import Customer
    from django.utils import timezone
    t = Tenant.objects.create(name="T", default_currency="usd")
    c = Customer.objects.create(tenant=t, external_id="c1")
    default = RateCard.objects.create(tenant=t, card_type="price", provider_key="gemini",
                                      currency="usd", key="gemini", is_default=True)
    ent = RateCard.objects.create(tenant=t, card_type="price", provider_key="gemini",
                                  currency="usd", key="ent")
    RateCardAssignment.objects.create(tenant=t, customer=c, rate_card=ent, currency="usd")
    # Enterprise overrides input_tokens; output_tokens only exists in default.
    ent_in = Rate.objects.create(tenant=t, provider="gemini",
                                 measurement=declares_a_quantity(t, "input_tokens"), currency="usd",
                                 rate_per_unit_micros=5, rate_card=ent)
    def_out = Rate.objects.create(tenant=t, provider="gemini",
                                  measurement=declares_a_quantity(t, "output_tokens"), currency="usd",
                                  rate_per_unit_micros=30, rate_card=default)
    # Conflicting default-book rate for the SAME quantity as ent_in — proves the
    # assigned book shadows the default book rather than resolving by
    # elimination (only possible because Rate uniqueness is now per-book).
    def_in = Rate.objects.create(tenant=t, provider="gemini",
                                 measurement=declares_a_quantity(t, "input_tokens"), currency="usd",
                                 rate_per_unit_micros=99, rate_card=default)
    now = timezone.now()
    selectors = {"provider": "gemini"}
    assert PricingService._resolve_card(t, c, "price", selectors, "input_tokens", "usd", now).id == ent_in.id
    assert PricingService._resolve_card(t, c, "price", selectors, "output_tokens", "usd", now).id == def_out.id


def test_no_default_book_for_provider_returns_none(db):
    from apps.metering.pricing.services.pricing_service import PricingService
    from apps.platform.tenants.models import Tenant
    from apps.platform.customers.models import Customer
    from django.utils import timezone
    t = Tenant.objects.create(name="T", default_currency="usd")
    c = Customer.objects.create(tenant=t, external_id="c1")
    assert PricingService._resolve_card(
        t, c, "price", {"provider": "openai"}, "input_tokens", "usd", timezone.now()) is None
