import pytest
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.tenants.models import Tenant
from core.vocabulary import RATE_STRUCTURE_FIXED_COMPONENT


@pytest.mark.django_db
class TestRateCard:
    def test_selectors_and_per_unit_compute(self):
        from apps.metering.pricing.models import Rate
        t = Tenant.objects.create(name="T")
        c = Rate.objects.create(
            tenant=t, card_type="cost", provider="openai", event_type="chat",
            measurement=declares_a_quantity(t, "input_tokens"), grouping_field_1="gpt-4",
            rate_structure="per_unit", rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        # provider, event_type and the first slot.
        assert c.grouping_field_1 == "gpt-4" and c.specificity == 3
        assert c.compute(1000) == 5  # (1000*5000 + 500000)//1000000 = 5
        c2 = Rate.objects.create(tenant=t, card_type="cost", measurement=declares_a_quantity(t, "m"),
                                     rate_per_unit_micros=1, unit_quantity=2)
        assert c2.compute(1) == 1 and c2.compute(0) == 0  # round-half-up midpoint

    def test_flat_compute_uses_fixed(self):
        from apps.metering.pricing.models import Rate
        t = Tenant.objects.create(name="T")
        c = Rate.objects.create(tenant=t, card_type="price", measurement=declares_a_quantity(t, "seats"),
                                    rate_structure=RATE_STRUCTURE_FIXED_COMPONENT, fixed_micros=2_000_000)
        assert c.compute(5) == 2_000_000

    def test_one_active_rate_per_book_slice(self):
        # Uniqueness is now book-scoped (rate_card is part of the constraint's
        # key, not tenant/customer): two active rates for the same
        # (provider, event_type, measurement_key, dimensions_hash, currency) in
        # the SAME book still collide.
        from django.db.utils import IntegrityError
        from apps.metering.pricing.models import Rate, RateCard
        t = Tenant.objects.create(name="T")
        book = RateCard.objects.create(tenant=t, card_type="cost", currency="usd", key="default")
        Rate.objects.create(tenant=t, card_type="cost", provider="openai",
                                event_type="chat", measurement=declares_a_quantity(t, "input_tokens"), rate_card=book)
        with pytest.raises(IntegrityError):
            Rate.objects.create(tenant=t, card_type="cost", provider="openai",
                                    event_type="chat", measurement=declares_a_quantity(t, "input_tokens"), rate_card=book)

    def test_same_metric_slice_in_different_books_does_not_conflict(self):
        # The entire point of book-scoped uniqueness: the SAME quantity may have
        # an active rate in two different books at once (e.g. an enterprise
        # book shadowing the tenant default for the same quantity).
        from apps.metering.pricing.models import Rate, RateCard
        t = Tenant.objects.create(name="T")
        book_a = RateCard.objects.create(tenant=t, card_type="cost", currency="usd", key="a")
        book_b = RateCard.objects.create(tenant=t, card_type="cost", currency="usd", key="b")
        Rate.objects.create(tenant=t, card_type="cost", provider="openai",
                                event_type="chat", measurement=declares_a_quantity(t, "input_tokens"), rate_card=book_a)
        # No IntegrityError: different rate_card, so the constraint doesn't fire.
        Rate.objects.create(tenant=t, card_type="cost", provider="openai",
                                event_type="chat", measurement=declares_a_quantity(t, "input_tokens"), rate_card=book_b)
