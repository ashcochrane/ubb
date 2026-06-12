from datetime import date, datetime, timezone as dt_timezone

import pytest
from django.db import transaction
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import PricingPeriodCounter, RateCard
from apps.metering.pricing.services.tier_counter_service import (
    TierCounterService, month_bounds,
)

TIERS = [{"up_to": None, "rate_per_unit_micros": 1, "unit_quantity": 1}]


def _setup():
    tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
    customer = Customer.objects.create(tenant=tenant, external_id="c1")
    card = RateCard.objects.create(
        tenant=tenant, card_type="price", metric_name="tok",
        pricing_model="graduated", tiers=TIERS)
    return tenant, customer, card


class TestMonthBounds:
    def test_mid_month(self):
        as_of = datetime(2026, 6, 12, 10, 30, tzinfo=dt_timezone.utc)
        assert month_bounds(as_of) == (date(2026, 6, 1), date(2026, 7, 1))

    def test_december_rollover(self):
        as_of = datetime(2026, 12, 31, 23, 59, tzinfo=dt_timezone.utc)
        assert month_bounds(as_of) == (date(2026, 12, 1), date(2027, 1, 1))


@pytest.mark.django_db
class TestLockAndAdvance:
    def test_advance_accumulates_and_keys_on_month(self):
        tenant, customer, card = _setup()
        now = timezone.now()
        assert TierCounterService.lock_and_advance(tenant, customer, card, 100, now) == (0, 100)
        assert TierCounterService.lock_and_advance(tenant, customer, card, 50, now) == (100, 150)
        counter = PricingPeriodCounter.objects.get(
            tenant=tenant, customer=customer, lineage_id=card.lineage_id)
        assert counter.units_total == 150
        assert (counter.period_start, counter.period_end) == month_bounds(now)
        assert counter.metric_name == "tok" and counter.currency == "usd"

    def test_zero_and_none_units_advance_nothing(self):
        tenant, customer, card = _setup()
        now = timezone.now()
        assert TierCounterService.lock_and_advance(tenant, customer, card, 0, now) == (0, 0)
        assert TierCounterService.lock_and_advance(tenant, customer, card, None, now) == (0, 0)

    def test_separate_months_get_separate_counters(self):
        tenant, customer, card = _setup()
        jan = datetime(2026, 1, 15, tzinfo=dt_timezone.utc)
        feb = datetime(2026, 2, 1, tzinfo=dt_timezone.utc)
        assert TierCounterService.lock_and_advance(tenant, customer, card, 10, jan) == (0, 10)
        assert TierCounterService.lock_and_advance(tenant, customer, card, 5, feb) == (0, 5)
        assert PricingPeriodCounter.objects.filter(customer=customer).count() == 2

    def test_separate_lineages_get_separate_counters(self):
        tenant, customer, card = _setup()
        other = RateCard.objects.create(
            tenant=tenant, card_type="price", metric_name="other_tok",
            pricing_model="graduated", tiers=TIERS)
        now = timezone.now()
        TierCounterService.lock_and_advance(tenant, customer, card, 10, now)
        assert TierCounterService.lock_and_advance(tenant, customer, other, 7, now) == (0, 7)
        assert PricingPeriodCounter.objects.filter(customer=customer).count() == 2


@pytest.mark.django_db(transaction=True)
class TestLockAndAdvanceTransactionGuard:
    def test_requires_open_transaction(self):
        tenant, customer, card = _setup()
        with pytest.raises(AssertionError, match="transaction.atomic"):
            TierCounterService.lock_and_advance(tenant, customer, card, 1, timezone.now())
        # and works as soon as a transaction is open
        with transaction.atomic():
            assert TierCounterService.lock_and_advance(
                tenant, customer, card, 1, timezone.now()) == (0, 1)
