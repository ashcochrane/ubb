import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.pricing.services.pricing_service import PricingService
from apps.metering.pricing.tests._helpers import rate_in_default_book


@pytest.mark.django_db
class TestWildcardResolution:
    def _tc(self):
        t = Tenant.objects.create(name="T")
        return t, Customer.objects.create(tenant=t, external_id="c1")

    def _price(self, t, c, **selectors):
        base = {"provider": "", "event_type": "", "task_type": "",
                "subtask_type": "", "dim1": "", "dim2": "", "dim3": "",
                "dim4": "", "dim5": "", "dim6": ""}
        base.update(selectors)
        return PricingService.price(
            tenant=t, customer=c, selectors=base,
            usage_metrics={"input_tokens": 1_000_000}, currency="usd",
            caller_provider_cost=None, caller_billed=None)

    def test_wildcard_rate_matches_any_provider(self):
        """The headline fix: one provider-agnostic rate, not one per provider."""
        t, c = self._tc()
        rate_in_default_book(t, card_type="cost", metric_name="input_tokens",
                             rate_per_unit_micros=2_000, unit_quantity=1_000_000)
        prov, _, p = self._price(t, c, provider="anthropic")
        assert prov == 2_000 and p["cost_source"] == "rate_card"

    def test_specific_rate_beats_the_wildcard(self):
        t, c = self._tc()
        rate_in_default_book(t, card_type="cost", metric_name="input_tokens",
                             rate_per_unit_micros=2_000, unit_quantity=1_000_000)
        rate_in_default_book(t, card_type="cost", provider="openai",
                             metric_name="input_tokens",
                             rate_per_unit_micros=9_000, unit_quantity=1_000_000)
        assert self._price(t, c, provider="openai")[0] == 9_000

    def test_wildcard_still_applies_to_other_providers(self):
        t, c = self._tc()
        rate_in_default_book(t, card_type="cost", metric_name="input_tokens",
                             rate_per_unit_micros=2_000, unit_quantity=1_000_000)
        rate_in_default_book(t, card_type="cost", provider="openai",
                             metric_name="input_tokens",
                             rate_per_unit_micros=9_000, unit_quantity=1_000_000)
        assert self._price(t, c, provider="anthropic")[0] == 2_000

    def test_more_pinned_selectors_wins(self):
        t, c = self._tc()
        rate_in_default_book(t, card_type="cost", provider="openai",
                             metric_name="input_tokens",
                             rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        rate_in_default_book(t, card_type="cost", provider="openai",
                             task_type="year_end_close", metric_name="input_tokens",
                             rate_per_unit_micros=1_000, unit_quantity=1_000_000)
        assert self._price(t, c, provider="openai",
                           task_type="year_end_close")[0] == 1_000

    def test_non_matching_pinned_selector_excludes_the_rate(self):
        t, c = self._tc()
        rate_in_default_book(t, card_type="cost", provider="openai",
                             dim1="eu-west-1", metric_name="input_tokens",
                             rate_per_unit_micros=1_000, unit_quantity=1_000_000)
        prov, _, p = self._price(t, c, provider="openai", dim1="us-east-1")
        assert prov == 0 and p["uncosted_metrics"] == ["input_tokens"]

    def test_task_type_can_price_a_kind_of_job(self):
        t, c = self._tc()
        rate_in_default_book(t, card_type="price", task_type="year_end_close",
                             metric_name="input_tokens",
                             rate_per_unit_micros=7_000, unit_quantity=1_000_000)
        _, billed, p = self._price(t, c, task_type="year_end_close")
        assert billed == 7_000 and p["price_source"] == "rate_card"

    def test_provider_book_present_but_no_matching_rate_falls_back_to_wildcard_book(self):
        """Pins the `_resolve_card` third cascade tier specifically: a
        provider-specific default book EXISTING (with a rate for a different
        metric) must not shadow the tenant's "" (provider-agnostic) default
        book for a metric only the wildcard book prices. This is the branch
        that changes pre-existing behaviour — before the fallback tier was
        added, `_default_book` picked the "openai" book (found), then found
        no matching rate for "metric_y" in it, and never looked at the ""
        book at all, so this fell through to markup. All the other tests in
        this file exercise "book absent" -> tier 3; this one exercises "book
        present, no matching rate" -> tier 3."""
        t, c = self._tc()
        rate_in_default_book(t, card_type="cost", provider="openai",
                             metric_name="metric_x",
                             rate_per_unit_micros=9_000, unit_quantity=1_000_000)
        rate_in_default_book(t, card_type="cost", metric_name="metric_y",
                             rate_per_unit_micros=3_000, unit_quantity=1_000_000)
        base = {"provider": "openai", "event_type": "", "task_type": "",
                "subtask_type": "", "dim1": "", "dim2": "", "dim3": "",
                "dim4": "", "dim5": "", "dim6": ""}
        prov, _, p = PricingService.price(
            tenant=t, customer=c, selectors=base,
            usage_metrics={"metric_y": 1_000_000}, currency="usd",
            caller_provider_cost=None, caller_billed=None)
        assert prov == 3_000 and p["cost_source"] == "rate_card"
