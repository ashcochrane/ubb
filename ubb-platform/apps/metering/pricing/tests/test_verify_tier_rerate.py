"""verify_tier_rerate: monthly tripwire — alert-only, never mutates.

The 'apps' logger does not propagate to root (pytest caplog would miss it),
so drift assertions patch the task module's logger directly.
"""
from unittest import mock

import pytest

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.pricing import tasks as pricing_tasks
from apps.metering.pricing.models import PricingPeriodCounter, Rate
from apps.metering.pricing.tasks import verify_tier_rerate, _previous_month_start
from apps.metering.pricing.tests._helpers import rate_in_default_book
from apps.metering.usage.models import UsageEvent
from apps.metering.usage.services.usage_service import UsageService

TIERS = [
    {"up_to": 100, "rate_per_unit_micros": 10, "unit_quantity": 1},
    {"up_to": None, "rate_per_unit_micros": 5, "unit_quantity": 1},
]


def _setup_period():
    tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
    customer = Customer.objects.create(tenant=tenant, external_id="c1")
    card = rate_in_default_book(
        tenant, card_type="price", metric_name="tok",
        pricing_model="graduated", tiers=TIERS)
    for i, units in enumerate([60, 50, 40]):
        UsageService.record_usage(tenant, customer, f"r{i}", f"k{i}",
                                  usage_metrics={"tok": units})
    counter = PricingPeriodCounter.objects.get(lineage_id=card.lineage_id)
    return tenant, customer, card, counter


def _run_and_collect_drift(period_start_iso=None):
    with mock.patch.object(pricing_tasks.logger, "error") as mock_error:
        verify_tier_rerate(period_start_iso=period_start_iso)
    return [call for call in mock_error.call_args_list
            if call.args[0] == "pricing.tier_rerate_drift"]


@pytest.mark.django_db
class TestVerifyTierRerate:
    def test_clean_period_is_silent(self):
        _, _, _, counter = _setup_period()
        drift = _run_and_collect_drift(counter.period_start.isoformat())
        assert drift == []

    def test_corrupted_counter_alerts_and_mutates_nothing(self):
        _, _, _, counter = _setup_period()
        corrupted_total = counter.units_total + 5
        PricingPeriodCounter.objects.filter(id=counter.id).update(
            units_total=corrupted_total)  # bypasses the service, like raw SQL
        drift = _run_and_collect_drift(counter.period_start.isoformat())
        assert len(drift) == 1
        problems = drift[0].kwargs["extra"]["data"]["problems"]
        assert any("units_total mismatch" in p for p in problems)
        # ALERT ONLY: the counter keeps its (corrupted) value, events untouched.
        counter.refresh_from_db()
        assert counter.units_total == corrupted_total
        assert UsageEvent.objects.count() == 3

    def test_chain_break_detected(self):
        _, _, _, counter = _setup_period()
        event = UsageEvent.objects.order_by("created_at").last()
        provenance = event.pricing_provenance
        provenance["metrics"][0]["tier_breakdown"]["prior_units"] += 1
        UsageEvent.objects.filter(id=event.id).update(
            pricing_provenance=provenance)  # tamper past immutability
        drift = _run_and_collect_drift(counter.period_start.isoformat())
        assert len(drift) == 1
        problems = drift[0].kwargs["extra"]["data"]["problems"]
        assert any("chain break" in p for p in problems)

    def test_rerate_mismatch_detected_for_single_version_period(self):
        _, _, _, counter = _setup_period()
        event = UsageEvent.objects.order_by("created_at").first()
        provenance = event.pricing_provenance
        provenance["metrics"][0]["micros"] += 1
        UsageEvent.objects.filter(id=event.id).update(pricing_provenance=provenance)
        drift = _run_and_collect_drift(counter.period_start.isoformat())
        assert len(drift) == 1
        problems = drift[0].kwargs["extra"]["data"]["problems"]
        assert any("re-rate mismatch" in p for p in problems)

    def test_default_period_is_previous_month_and_silent_when_empty(self):
        _setup_period()  # counters live in the CURRENT month
        drift = _run_and_collect_drift()  # previous month: no counters
        assert drift == []


class TestPreviousMonthStart:
    def test_mid_year(self):
        from datetime import date
        assert _previous_month_start(date(2026, 6, 12)) == date(2026, 5, 1)

    def test_january_rolls_to_december(self):
        from datetime import date
        assert _previous_month_start(date(2026, 1, 15)) == date(2025, 12, 1)
