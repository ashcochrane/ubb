import pytest
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestRateCard:
    def test_dimensions_hash_and_per_unit_compute(self):
        from apps.metering.pricing.models import Rate
        t = Tenant.objects.create(name="T")
        c = Rate.objects.create(
            tenant=t, card_type="cost", provider="openai", event_type="chat",
            metric_name="input_tokens", dimensions={"model": "gpt-4"},
            pricing_model="per_unit", rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        assert c.dimensions_hash and len(c.dimensions_hash) == 64
        assert c.compute(1000) == 5  # (1000*5000 + 500000)//1000000 = 5
        c2 = Rate.objects.create(tenant=t, card_type="cost", metric_name="m",
                                     rate_per_unit_micros=1, unit_quantity=2)
        assert c2.compute(1) == 1 and c2.compute(0) == 0  # round-half-up midpoint

    def test_flat_compute_uses_fixed(self):
        from apps.metering.pricing.models import Rate
        t = Tenant.objects.create(name="T")
        c = Rate.objects.create(tenant=t, card_type="price", metric_name="seats",
                                    pricing_model="flat", fixed_micros=2_000_000)
        assert c.compute(5) == 2_000_000

    def test_one_active_rate_per_book_slice(self):
        # Uniqueness is now book-scoped (rate_card is part of the constraint's
        # key, not tenant/customer): two active rates for the same
        # (provider, event_type, metric_name, dimensions_hash, currency) in
        # the SAME book still collide.
        from django.db.utils import IntegrityError
        from apps.metering.pricing.models import Rate, RateCard
        t = Tenant.objects.create(name="T")
        book = RateCard.objects.create(tenant=t, card_type="cost", currency="usd", key="default")
        Rate.objects.create(tenant=t, card_type="cost", provider="openai",
                                event_type="chat", metric_name="input_tokens", rate_card=book)
        with pytest.raises(IntegrityError):
            Rate.objects.create(tenant=t, card_type="cost", provider="openai",
                                    event_type="chat", metric_name="input_tokens", rate_card=book)

    def test_same_metric_slice_in_different_books_does_not_conflict(self):
        # The entire point of book-scoped uniqueness: the SAME metric may have
        # an active rate in two different books at once (e.g. an enterprise
        # book shadowing the tenant default for the same metric).
        from apps.metering.pricing.models import Rate, RateCard
        t = Tenant.objects.create(name="T")
        book_a = RateCard.objects.create(tenant=t, card_type="cost", currency="usd", key="a")
        book_b = RateCard.objects.create(tenant=t, card_type="cost", currency="usd", key="b")
        Rate.objects.create(tenant=t, card_type="cost", provider="openai",
                                event_type="chat", metric_name="input_tokens", rate_card=book_a)
        # No IntegrityError: different rate_card, so the constraint doesn't fire.
        Rate.objects.create(tenant=t, card_type="cost", provider="openai",
                                event_type="chat", metric_name="input_tokens", rate_card=book_b)
