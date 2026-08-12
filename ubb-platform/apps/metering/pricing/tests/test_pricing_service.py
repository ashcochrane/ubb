import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import Rate, TenantMarkup
from apps.metering.pricing.services.pricing_service import PricingService, PricingError
from apps.metering.pricing.tests._helpers import rate_in_default_book


@pytest.mark.django_db
class TestPricing:
    def _t(self, **kw):
        return Tenant.objects.create(name="T", **kw)

    def test_caller_cost_wins_then_markup(self):
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        TenantMarkup.objects.create(tenant=t, markup_percentage_micros=20_000_000)
        prov, billed, p = PricingService.price(
            tenant=t, customer=c, selectors={"event_type": "chat", "provider": "openai"},
            measurements=None, currency="usd",
            caller_provider_cost=1_000_000, caller_billed=None)
        assert prov == 1_000_000 and billed == 1_200_000 and p["price_source"] == "markup"

    def test_cost_card_computes_provider_when_no_caller_cost(self):
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        rate_in_default_book(t, card_type="cost", provider="openai", event_type="chat",
            measurement_key="input_tokens", grouping_field_1="gpt-4",
            rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        prov, billed, p = PricingService.price(
            tenant=t, customer=c,
            selectors={"event_type": "chat", "provider": "openai",
                       "grouping_field_1": "gpt-4"},
            measurements={"input_tokens": 1000}, currency="usd",
            caller_provider_cost=None, caller_billed=None)
        assert prov == 5 and billed == 5

    def test_price_card_charges_on_different_metric(self):
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        rate_in_default_book(t, card_type="cost", provider="openai", event_type="chat",
            measurement_key="input_tokens", rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        rate_in_default_book(t, card_type="price", provider="openai", event_type="chat",
            measurement_key="seats", pricing_model="flat", fixed_micros=9_000_000)
        prov, billed, p = PricingService.price(
            tenant=t, customer=c, selectors={"event_type": "chat", "provider": "openai"},
            measurements={"input_tokens": 1000, "seats": 3}, currency="usd",
            caller_provider_cost=None, caller_billed=None)
        assert prov == 5 and billed == 9_000_000 and p["price_source"] == "rate_card"

    def test_most_specific_dimension_wins_and_wildcard_fallback(self):
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        rate_in_default_book(t, card_type="cost", provider="o", event_type="e",
            measurement_key="tok", rate_per_unit_micros=1_000, unit_quantity=1_000_000)
        rate_in_default_book(t, card_type="cost", provider="o", event_type="e",
            measurement_key="tok", grouping_field_1="gpt-4", rate_per_unit_micros=9_000, unit_quantity=1_000_000)
        prov, _, _ = PricingService.price(
            tenant=t, customer=c,
            selectors={"event_type": "e", "provider": "o",
                       "grouping_field_1": "gpt-4"},
            measurements={"tok": 1_000_000}, currency="usd",
            caller_provider_cost=None, caller_billed=None)
        assert prov == 9_000
        prov2, _, _ = PricingService.price(
            tenant=t, customer=c,
            selectors={"event_type": "e", "provider": "o",
                       "grouping_field_1": "other"},
            measurements={"tok": 1_000_000}, currency="usd",
            caller_provider_cost=None, caller_billed=None)
        assert prov2 == 1_000

    def test_missing_cost_card_permissive_zero_then_strict_raises(self):
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        prov, billed, p = PricingService.price(
            tenant=t, customer=c, selectors={"event_type": "e", "provider": "o"},
            measurements={"tok": 100}, currency="usd",
            caller_provider_cost=None, caller_billed=None)
        assert prov == 0 and p["uncosted_metrics"] == ["tok"]
        t.require_cost_card_coverage = True; t.save(update_fields=["require_cost_card_coverage"])
        with pytest.raises(PricingError):
            PricingService.price(
                tenant=t, customer=c, selectors={"event_type": "e", "provider": "o"},
                measurements={"tok": 100}, currency="usd",
                caller_provider_cost=None, caller_billed=None)

    def test_caller_cost_path_respects_coverage_when_strict(self):
        # Strict flag ON + quantity with no cost card + caller-supplied provider cost
        # must still raise PricingError (the bypass was silently skipping the coverage check).
        t = self._t()
        t.require_cost_card_coverage = True
        t.save(update_fields=["require_cost_card_coverage"])
        c = Customer.objects.create(tenant=t, external_id="c2")
        with pytest.raises(PricingError):
            PricingService.price(
                tenant=t, customer=c, selectors={"event_type": "e", "provider": "o"},
                measurements={"unmatched_metric": 100}, currency="usd",
                caller_provider_cost=500, caller_billed=None,
            )

    def test_caller_cost_path_strict_flag_off_does_not_raise(self):
        # Strict flag OFF: caller-cost path must not raise even if metrics have no cost card.
        t = self._t()  # require_cost_card_coverage defaults to False
        c = Customer.objects.create(tenant=t, external_id="c3")
        prov, billed, p = PricingService.price(
            tenant=t, customer=c, selectors={"event_type": "e", "provider": "o"},
            measurements={"unmatched_metric": 100}, currency="usd",
            caller_provider_cost=500, caller_billed=None,
        )
        assert prov == 500 and p["cost_source"] == "caller"

    def test_caller_cost_path_strict_all_metrics_covered_does_not_raise(self):
        # Strict flag ON but all metrics have a cost card: caller-cost path must not raise.
        t = self._t()
        t.require_cost_card_coverage = True
        t.save(update_fields=["require_cost_card_coverage"])
        c = Customer.objects.create(tenant=t, external_id="c4")
        rate_in_default_book(t, card_type="cost", provider="o", event_type="e",
            measurement_key="tok", rate_per_unit_micros=1_000, unit_quantity=1_000_000)
        prov, billed, p = PricingService.price(
            tenant=t, customer=c, selectors={"event_type": "e", "provider": "o"},
            measurements={"tok": 100}, currency="usd",
            caller_provider_cost=500, caller_billed=None,
        )
        assert prov == 500 and p["cost_source"] == "caller"

    # ---- Strict coverage, after F2.4's second refusal retired with its input ----
    #
    # That refusal rejected an event which declared a nameless magnitude and no
    # quantity name to resolve a rate card against. #272 deleted the magnitude, so
    # the refusal is not relaxed here — it has become unexpressible, and the
    # tests that drove it went with it. What remains is proved below: an event
    # with nothing to price is a marker and is accepted in either mode, and an
    # event that DOES name its quantities is refused exactly as before.

    @pytest.mark.parametrize("strict", [True, False])
    def test_nothing_to_price_is_a_marker_event(self, strict):
        """No quantities and no caller cost → accepted at zero, strict or not.

        This was already the answer whenever the retired magnitude was zero or
        omitted, which is what every such request now is. The refusal only ever
        fired above zero, so no request that used to be rejected can still be
        made — which is the whole reason deleting the branch changes no verdict.
        """
        t = self._t()
        t.require_cost_card_coverage = strict
        t.save(update_fields=["require_cost_card_coverage"])
        c = Customer.objects.create(tenant=t, external_id=f"c5-{strict}")
        prov, billed, p = PricingService.price(
            tenant=t, customer=c,
            selectors={"event_type": "e", "provider": "o"},
            measurements=None, currency="usd",
            caller_provider_cost=None, caller_billed=None)
        assert prov == 0

    def test_caller_cost_with_no_metrics_is_still_accepted_in_strict_mode(self):
        # Cost is explicitly known, so there is nothing for coverage to enforce.
        t = self._t()
        t.require_cost_card_coverage = True
        t.save(update_fields=["require_cost_card_coverage"])
        c = Customer.objects.create(tenant=t, external_id="c7")
        prov, billed, p = PricingService.price(
            tenant=t, customer=c, selectors={"event_type": "e", "provider": "o"},
            measurements=None, currency="usd",
            caller_provider_cost=123, caller_billed=None)
        assert prov == 123 and p["cost_source"] == "caller"

    def test_strict_uncovered_metric_still_raises_via_existing_gate(self):
        # THE GUARANTEE THAT SURVIVES, and the one that was always load-bearing:
        # an event that names a quantity UBB cannot cost is refused. Untouched by
        # #272 — this branch never read the retired magnitude.
        t = self._t()
        t.require_cost_card_coverage = True
        t.save(update_fields=["require_cost_card_coverage"])
        c = Customer.objects.create(tenant=t, external_id="c10")
        with pytest.raises(PricingError):
            PricingService.price(
                tenant=t, customer=c, selectors={"event_type": "e", "provider": "o"},
                measurements={"unmatched": 5}, currency="usd",
                caller_provider_cost=None, caller_billed=None)


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
    r = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                            measurement_key="input_tokens", currency="usd",
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
    ent_in = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                                 measurement_key="input_tokens", currency="usd",
                                 rate_per_unit_micros=5, rate_card=ent)
    def_out = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                                  measurement_key="output_tokens", currency="usd",
                                  rate_per_unit_micros=30, rate_card=default)
    # Conflicting default-book rate for the SAME quantity as ent_in — proves the
    # assigned book shadows the default book rather than resolving by
    # elimination (only possible because Rate uniqueness is now per-book).
    def_in = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                                 measurement_key="input_tokens", currency="usd",
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
