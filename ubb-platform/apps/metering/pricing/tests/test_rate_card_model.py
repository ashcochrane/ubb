import pytest
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestRateCard:
    def test_dimensions_hash_and_per_unit_compute(self):
        from apps.metering.pricing.models import RateCard
        t = Tenant.objects.create(name="T")
        c = RateCard.objects.create(
            tenant=t, card_type="cost", provider="openai", event_type="chat",
            metric_name="input_tokens", dimensions={"model": "gpt-4"},
            pricing_model="per_unit", rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        assert c.dimensions_hash and len(c.dimensions_hash) == 64
        assert c.compute(1000) == 5  # (1000*5000 + 500000)//1000000 = 5
        c2 = RateCard.objects.create(tenant=t, card_type="cost", metric_name="m",
                                     rate_per_unit_micros=1, unit_quantity=2)
        assert c2.compute(1) == 1 and c2.compute(0) == 0  # round-half-up midpoint

    def test_flat_compute_uses_fixed(self):
        from apps.metering.pricing.models import RateCard
        t = Tenant.objects.create(name="T")
        c = RateCard.objects.create(tenant=t, card_type="price", metric_name="seats",
                                    pricing_model="flat", fixed_micros=2_000_000)
        assert c.compute(5) == 2_000_000

    def test_one_active_tenant_default_per_slice(self):
        from django.db.utils import IntegrityError
        from apps.metering.pricing.models import RateCard
        t = Tenant.objects.create(name="T")
        RateCard.objects.create(tenant=t, card_type="cost", provider="openai",
                                event_type="chat", metric_name="input_tokens")
        with pytest.raises(IntegrityError):
            RateCard.objects.create(tenant=t, card_type="cost", provider="openai",
                                    event_type="chat", metric_name="input_tokens")
