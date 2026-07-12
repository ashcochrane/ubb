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
            tenant=t, customer=c, event_type="chat", provider="openai",
            usage_metrics=None, tags=None, currency="usd",
            caller_provider_cost=1_000_000, caller_billed=None)
        assert prov == 1_000_000 and billed == 1_200_000 and p["price_source"] == "markup"

    def test_cost_card_computes_provider_when_no_caller_cost(self):
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        rate_in_default_book(t, card_type="cost", provider="openai", event_type="chat",
            metric_name="input_tokens", dimensions={"model": "gpt-4"},
            rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        prov, billed, p = PricingService.price(
            tenant=t, customer=c, event_type="chat", provider="openai",
            usage_metrics={"input_tokens": 1000}, tags={"model": "gpt-4"}, currency="usd",
            caller_provider_cost=None, caller_billed=None)
        assert prov == 5 and billed == 5

    def test_price_card_charges_on_different_metric(self):
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        rate_in_default_book(t, card_type="cost", provider="openai", event_type="chat",
            metric_name="input_tokens", rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        rate_in_default_book(t, card_type="price", provider="openai", event_type="chat",
            metric_name="seats", pricing_model="flat", fixed_micros=9_000_000)
        prov, billed, p = PricingService.price(
            tenant=t, customer=c, event_type="chat", provider="openai",
            usage_metrics={"input_tokens": 1000, "seats": 3}, tags=None, currency="usd",
            caller_provider_cost=None, caller_billed=None)
        assert prov == 5 and billed == 9_000_000 and p["price_source"] == "rate_card"

    def test_most_specific_dimension_wins_and_wildcard_fallback(self):
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        rate_in_default_book(t, card_type="cost", provider="o", event_type="e",
            metric_name="tok", dimensions={}, rate_per_unit_micros=1_000, unit_quantity=1_000_000)
        rate_in_default_book(t, card_type="cost", provider="o", event_type="e",
            metric_name="tok", dimensions={"model": "gpt-4"}, rate_per_unit_micros=9_000, unit_quantity=1_000_000)
        prov, _, _ = PricingService.price(tenant=t, customer=c, event_type="e", provider="o",
            usage_metrics={"tok": 1_000_000}, tags={"model": "gpt-4"}, currency="usd",
            caller_provider_cost=None, caller_billed=None)
        assert prov == 9_000
        prov2, _, _ = PricingService.price(tenant=t, customer=c, event_type="e", provider="o",
            usage_metrics={"tok": 1_000_000}, tags={"model": "other"}, currency="usd",
            caller_provider_cost=None, caller_billed=None)
        assert prov2 == 1_000

    def test_missing_cost_card_permissive_zero_then_strict_raises(self):
        t = self._t(); c = Customer.objects.create(tenant=t, external_id="c1")
        prov, billed, p = PricingService.price(tenant=t, customer=c, event_type="e", provider="o",
            usage_metrics={"tok": 100}, tags=None, currency="usd",
            caller_provider_cost=None, caller_billed=None)
        assert prov == 0 and p["uncosted_metrics"] == ["tok"]
        t.require_cost_card_coverage = True; t.save(update_fields=["require_cost_card_coverage"])
        with pytest.raises(PricingError):
            PricingService.price(tenant=t, customer=c, event_type="e", provider="o",
                usage_metrics={"tok": 100}, tags=None, currency="usd",
                caller_provider_cost=None, caller_billed=None)

    def test_caller_cost_path_respects_coverage_when_strict(self):
        # Strict flag ON + metric with no cost card + caller-supplied provider cost
        # must still raise PricingError (the bypass was silently skipping the coverage check).
        t = self._t()
        t.require_cost_card_coverage = True
        t.save(update_fields=["require_cost_card_coverage"])
        c = Customer.objects.create(tenant=t, external_id="c2")
        with pytest.raises(PricingError):
            PricingService.price(
                tenant=t, customer=c, event_type="e", provider="o",
                usage_metrics={"unmatched_metric": 100}, tags=None, currency="usd",
                caller_provider_cost=500, caller_billed=None,
            )

    def test_caller_cost_path_strict_flag_off_does_not_raise(self):
        # Strict flag OFF: caller-cost path must not raise even if metrics have no cost card.
        t = self._t()  # require_cost_card_coverage defaults to False
        c = Customer.objects.create(tenant=t, external_id="c3")
        prov, billed, p = PricingService.price(
            tenant=t, customer=c, event_type="e", provider="o",
            usage_metrics={"unmatched_metric": 100}, tags=None, currency="usd",
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
            metric_name="tok", rate_per_unit_micros=1_000, unit_quantity=1_000_000)
        prov, billed, p = PricingService.price(
            tenant=t, customer=c, event_type="e", provider="o",
            usage_metrics={"tok": 100}, tags=None, currency="usd",
            caller_provider_cost=500, caller_billed=None,
        )
        assert prov == 500 and p["cost_source"] == "caller"

    # ---- F2.4: units-only strict coverage gate ----

    def test_units_no_metrics_strict_raises(self):
        # Strict ON + units > 0 + no usage_metrics → PricingError.
        t = self._t()
        t.require_cost_card_coverage = True
        t.save(update_fields=["require_cost_card_coverage"])
        c = Customer.objects.create(tenant=t, external_id="c5")
        with pytest.raises(PricingError, match="strict cost coverage"):
            PricingService.price(
                tenant=t, customer=c, event_type="e", provider="o",
                usage_metrics=None, tags=None, currency="usd",
                caller_provider_cost=None, caller_billed=None, units=5)

    def test_units_no_metrics_strict_off_returns_zero(self):
        # Strict OFF + units > 0 + no usage_metrics → accepted, cost = 0.
        t = self._t()  # require_cost_card_coverage defaults False
        c = Customer.objects.create(tenant=t, external_id="c6")
        prov, billed, p = PricingService.price(
            tenant=t, customer=c, event_type="e", provider="o",
            usage_metrics=None, tags=None, currency="usd",
            caller_provider_cost=None, caller_billed=None, units=5)
        assert prov == 0

    def test_units_with_caller_cost_strict_accepted(self):
        # Strict ON + units > 0 + no usage_metrics BUT caller supplies provider_cost_micros
        # → cost is known; must be accepted.
        t = self._t()
        t.require_cost_card_coverage = True
        t.save(update_fields=["require_cost_card_coverage"])
        c = Customer.objects.create(tenant=t, external_id="c7")
        prov, billed, p = PricingService.price(
            tenant=t, customer=c, event_type="e", provider="o",
            usage_metrics=None, tags=None, currency="usd",
            caller_provider_cost=123, caller_billed=None, units=5)
        assert prov == 123 and p["cost_source"] == "caller"

    def test_zero_units_no_metrics_strict_accepted(self):
        # Strict ON + units = 0 + no usage_metrics → marker event, must be accepted.
        t = self._t()
        t.require_cost_card_coverage = True
        t.save(update_fields=["require_cost_card_coverage"])
        c = Customer.objects.create(tenant=t, external_id="c8")
        prov, billed, p = PricingService.price(
            tenant=t, customer=c, event_type="e", provider="o",
            usage_metrics=None, tags=None, currency="usd",
            caller_provider_cost=None, caller_billed=None, units=0)
        assert prov == 0

    def test_none_units_no_metrics_strict_accepted(self):
        # Strict ON + units = None + no usage_metrics → marker event, must be accepted.
        t = self._t()
        t.require_cost_card_coverage = True
        t.save(update_fields=["require_cost_card_coverage"])
        c = Customer.objects.create(tenant=t, external_id="c9")
        prov, billed, p = PricingService.price(
            tenant=t, customer=c, event_type="e", provider="o",
            usage_metrics=None, tags=None, currency="usd",
            caller_provider_cost=None, caller_billed=None, units=None)
        assert prov == 0

    def test_strict_uncovered_metric_still_raises_via_existing_gate(self):
        # Regression: strict + usage_metrics with an uncovered metric → 422 via the
        # existing uncosted gate (unchanged behavior — the new gate must not interfere).
        t = self._t()
        t.require_cost_card_coverage = True
        t.save(update_fields=["require_cost_card_coverage"])
        c = Customer.objects.create(tenant=t, external_id="c10")
        with pytest.raises(PricingError):
            PricingService.price(
                tenant=t, customer=c, event_type="e", provider="o",
                usage_metrics={"unmatched": 5}, tags=None, currency="usd",
                caller_provider_cost=None, caller_billed=None, units=5)


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
                            metric_name="input_tokens", currency="usd",
                            rate_per_unit_micros=10, rate_card=book)
    got = PricingService._resolve_card(t, c, "price", "gemini", "",
                                       "input_tokens", {}, "usd", timezone.now())
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
                                 metric_name="input_tokens", currency="usd",
                                 rate_per_unit_micros=5, rate_card=ent)
    def_out = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                                  metric_name="output_tokens", currency="usd",
                                  rate_per_unit_micros=30, rate_card=default)
    # Conflicting default-book rate for the SAME metric as ent_in — proves the
    # assigned book shadows the default book rather than resolving by
    # elimination (only possible because Rate uniqueness is now per-book).
    def_in = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                                 metric_name="input_tokens", currency="usd",
                                 rate_per_unit_micros=99, rate_card=default)
    now = timezone.now()
    assert PricingService._resolve_card(t, c, "price", "gemini", "", "input_tokens", {}, "usd", now).id == ent_in.id
    assert PricingService._resolve_card(t, c, "price", "gemini", "", "output_tokens", {}, "usd", now).id == def_out.id


def test_no_default_book_for_provider_returns_none(db):
    from apps.metering.pricing.services.pricing_service import PricingService
    from apps.platform.tenants.models import Tenant
    from apps.platform.customers.models import Customer
    from django.utils import timezone
    t = Tenant.objects.create(name="T", default_currency="usd")
    c = Customer.objects.create(tenant=t, external_id="c1")
    assert PricingService._resolve_card(t, c, "price", "openai", "", "input_tokens", {}, "usd", timezone.now()) is None
