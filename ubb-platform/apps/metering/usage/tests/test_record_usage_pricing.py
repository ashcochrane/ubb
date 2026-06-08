import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import RateCard
from apps.metering.usage.services.usage_service import UsageService


@pytest.mark.django_db
class TestRecordUsagePricing:
    def test_backward_compat_caller_cost_unchanged(self):
        t = Tenant.objects.create(name="T"); c = Customer.objects.create(tenant=t, external_id="c1")
        r = UsageService.record_usage(t, c, "r1", "i1", provider_cost_micros=4_000)
        assert r["provider_cost_micros"] == 4_000 and r["billed_cost_micros"] == 4_000

    def test_priced_from_cost_card_when_no_caller_cost(self):
        t = Tenant.objects.create(name="T"); c = Customer.objects.create(tenant=t, external_id="c1")
        RateCard.objects.create(tenant=t, card_type="cost", provider="openai", event_type="chat",
            metric_name="input_tokens", rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        r = UsageService.record_usage(t, c, "r1", "i1", provider_cost_micros=None,
            provider="openai", event_type="chat", usage_metrics={"input_tokens": 1000})
        assert r["provider_cost_micros"] == 5 and r["billed_cost_micros"] == 5
        from apps.metering.usage.models import UsageEvent
        e = UsageEvent.objects.get(id=r["event_id"])
        assert e.usage_metrics == {"input_tokens": 1000}
        assert e.pricing_provenance["cost_source"] == "rate_card"
