"""Tiered pricing through the record_usage choke point.

Covers marginal rating, idempotency replay (fast path AND raced savepoint
path — the test that proves the price-inside-savepoint restructure),
per-lineage counter composition, provenance shape, and the cost-card guard.
"""
from unittest import mock

import pytest
from django.db import IntegrityError

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.runs.models import Run
from apps.metering.pricing.models import PricingPeriodCounter, RateCard
from apps.metering.pricing.services.pricing_service import PricingError
from apps.metering.usage.models import UsageEvent
from apps.metering.usage.services.usage_service import UsageService

TIERS = [
    {"up_to": 100, "rate_per_unit_micros": 10, "unit_quantity": 1},
    {"up_to": None, "rate_per_unit_micros": 5, "unit_quantity": 1},
]


def _setup():
    tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
    customer = Customer.objects.create(tenant=tenant, external_id="c1")
    card = RateCard.objects.create(
        tenant=tenant, card_type="price", metric_name="tok",
        pricing_model="graduated", tiers=TIERS)
    return tenant, customer, card


def _counter(card):
    return PricingPeriodCounter.objects.get(lineage_id=card.lineage_id)


@pytest.mark.django_db
class TestTieredRecordUsage:
    def test_marginal_pricing_across_events(self):
        tenant, customer, card = _setup()
        r1 = UsageService.record_usage(tenant, customer, "r1", "k1",
                                       usage_metrics={"tok": 60})
        assert r1["billed_cost_micros"] == 600          # 60 @10
        r2 = UsageService.record_usage(tenant, customer, "r2", "k2",
                                       usage_metrics={"tok": 60})
        assert r2["billed_cost_micros"] == 500          # 40 @10 + 20 @5
        assert _counter(card).units_total == 120
        # telescoping: sum of events == closed form on the period total
        assert 600 + 500 == card.compute_cumulative(120)

    def test_package_marginal_zero_inside_block(self):
        tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        card = RateCard.objects.create(
            tenant=tenant, card_type="price", metric_name="calls",
            pricing_model="package", rate_per_unit_micros=2_000_000,
            unit_quantity=1_000, tiers=[])
        r1 = UsageService.record_usage(tenant, customer, "r1", "k1",
                                       usage_metrics={"calls": 1})
        assert r1["billed_cost_micros"] == 2_000_000    # buys block 1
        r2 = UsageService.record_usage(tenant, customer, "r2", "k2",
                                       usage_metrics={"calls": 500})
        assert r2["billed_cost_micros"] == 0            # inside block 1 — correct
        r3 = UsageService.record_usage(tenant, customer, "r3", "k3",
                                       usage_metrics={"calls": 600})
        assert r3["billed_cost_micros"] == 2_000_000    # crosses into block 2
        assert _counter(card).units_total == 1_101
        assert card.compute_cumulative(1_101) == 4_000_000

    def test_two_tiered_metrics_in_one_event(self):
        tenant, customer, card = _setup()
        other = RateCard.objects.create(
            tenant=tenant, card_type="price", metric_name="alt",
            pricing_model="graduated", tiers=TIERS)
        r = UsageService.record_usage(tenant, customer, "r1", "k1",
                                      usage_metrics={"tok": 60, "alt": 150})
        assert r["billed_cost_micros"] == 600 + 1_250
        assert _counter(card).units_total == 60
        assert _counter(other).units_total == 150

    # ---- replay idempotency ----

    def test_replay_fast_path_counter_advances_once(self):
        tenant, customer, card = _setup()
        r1 = UsageService.record_usage(tenant, customer, "r1", "dup",
                                       usage_metrics={"tok": 60})
        r2 = UsageService.record_usage(tenant, customer, "r1", "dup",
                                       usage_metrics={"tok": 60})
        assert r2["event_id"] == r1["event_id"]
        assert r2["billed_cost_micros"] == 600
        assert _counter(card).units_total == 60
        assert UsageEvent.objects.filter(tenant=tenant, customer=customer).count() == 1

    def test_replay_race_path_rolls_back_counter_and_run_cost(self):
        """THE restructure proof: a duplicate insert that lands between the
        fast-path pre-check and the event create must roll back the counter
        advance and the run-cost accumulation with the savepoint."""
        tenant, customer, card = _setup()
        UsageService.record_usage(tenant, customer, "r1", "k1",
                                  usage_metrics={"tok": 60})
        run = Run.objects.create(tenant=tenant, customer=customer, status="active",
                                 balance_snapshot_micros=10_000_000)

        real_resolve = Customer.resolve_billing_owner

        def inject_duplicate(self_customer):
            # Simulate another writer winning the race AFTER the pre-check:
            # this runs between the idempotency pre-check and the savepoint.
            if not UsageEvent.objects.filter(
                    tenant=tenant, customer=customer,
                    idempotency_key="k2").exists():
                UsageEvent.objects.create(
                    tenant=tenant, customer=customer, request_id="other-writer",
                    idempotency_key="k2", provider_cost_micros=7,
                    billed_cost_micros=7, billing_owner_id=customer.id)
            return real_resolve(self_customer)

        with mock.patch.object(Customer, "resolve_billing_owner", inject_duplicate):
            result = UsageService.record_usage(
                tenant, customer, "r2", "k2",
                usage_metrics={"tok": 60}, run_id=run.id)

        # The raced duplicate is returned, not a freshly priced event.
        assert result["billed_cost_micros"] == 7
        # Counter UNCHANGED: the savepoint rolled the advance back.
        assert _counter(card).units_total == 60
        # No run-cost leak: accumulation rolled back with the savepoint.
        run.refresh_from_db()
        assert run.total_cost_micros == 0 and run.event_count == 0
        assert UsageEvent.objects.filter(
            tenant=tenant, customer=customer, idempotency_key="k2").count() == 1

    def test_non_duplicate_integrity_error_reraises(self):
        """A counter/run-machinery IntegrityError (no duplicate event exists)
        must surface attributably — not be masked as a replay."""
        tenant, customer, card = _setup()
        with mock.patch.object(UsageEvent.objects, "create",
                               side_effect=IntegrityError("boom")):
            with pytest.raises(IntegrityError, match="boom"):
                UsageService.record_usage(tenant, customer, "r1", "k1",
                                          usage_metrics={"tok": 60})

    # ---- composition: each card advances ONLY its own lineage ladder ----

    def test_each_resolved_card_advances_only_its_own_lineage(self):
        tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        seat_override = Customer.objects.create(tenant=tenant, external_id="c-override")
        seat_plain = Customer.objects.create(tenant=tenant, external_id="c-plain")
        default_card = RateCard.objects.create(
            tenant=tenant, card_type="price", metric_name="tok",
            pricing_model="graduated", tiers=TIERS)
        override_card = RateCard.objects.create(
            tenant=tenant, customer=seat_override, card_type="price",
            metric_name="tok", pricing_model="graduated", tiers=TIERS)
        dimensional_card = RateCard.objects.create(
            tenant=tenant, card_type="price", metric_name="tok",
            dimensions={"model": "gpt-4"}, pricing_model="graduated", tiers=TIERS)

        UsageService.record_usage(tenant, seat_override, "r1", "k1",
                                  usage_metrics={"tok": 10})
        UsageService.record_usage(tenant, seat_plain, "r2", "k2",
                                  usage_metrics={"tok": 20})
        UsageService.record_usage(tenant, seat_plain, "r3", "k3",
                                  usage_metrics={"tok": 30}, tags={"model": "gpt-4"})

        assert _counter(override_card).units_total == 10
        assert _counter(default_card).units_total == 20
        assert _counter(dimensional_card).units_total == 30
        assert PricingPeriodCounter.objects.count() == 3

    # ---- provenance ----

    def test_provenance_tier_breakdown_shape_and_band_sum(self):
        tenant, customer, card = _setup()
        r = UsageService.record_usage(tenant, customer, "r1", "k1",
                                      usage_metrics={"tok": 150})
        event = UsageEvent.objects.get(id=r["event_id"])
        price_entries = [m for m in event.pricing_provenance["metrics"]
                         if m["card_type"] == "price"]
        assert len(price_entries) == 1
        entry = price_entries[0]
        assert entry["pricing_model"] == "graduated"
        assert entry["micros"] == 1_250   # 100 @10 + 50 @5
        breakdown = entry["tier_breakdown"]
        assert breakdown["prior_units"] == 0
        assert breakdown["units_total_after"] == 150
        assert breakdown["cumulative_before_micros"] == 0
        assert breakdown["cumulative_after_micros"] == 1_250
        assert breakdown["lineage_id"] == str(card.lineage_id)
        assert breakdown["period_start"]  # ISO date string
        bands = breakdown["bands"]
        assert [b["up_to"] for b in bands] == [100, None]
        assert [b["units_in_band"] for b in bands] == [100, 50]
        assert sum(b["micros"] for b in bands) == entry["micros"]

    def test_provenance_band_sum_holds_for_partial_band_event(self):
        tenant, customer, card = _setup()
        UsageService.record_usage(tenant, customer, "r1", "k1",
                                  usage_metrics={"tok": 60})
        r2 = UsageService.record_usage(tenant, customer, "r2", "k2",
                                       usage_metrics={"tok": 60})
        event = UsageEvent.objects.get(id=r2["event_id"])
        entry = [m for m in event.pricing_provenance["metrics"]
                 if m["card_type"] == "price"][0]
        breakdown = entry["tier_breakdown"]
        assert breakdown["prior_units"] == 60
        assert breakdown["units_total_after"] == 120
        bands = breakdown["bands"]
        assert [b["units_in_band"] for b in bands] == [40, 20]
        assert sum(b["micros"] for b in bands) == entry["micros"] == 500

    # ---- cost-card guard ----

    def test_hand_crafted_tiered_cost_card_raises_pricing_error(self):
        tenant = Tenant.objects.create(name="T", products=["metering"])
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        RateCard.objects.create(  # bypasses endpoint validation on purpose
            tenant=tenant, card_type="cost", metric_name="tok",
            pricing_model="graduated", tiers=TIERS)
        with pytest.raises(PricingError, match="cost cards"):
            UsageService.record_usage(tenant, customer, "r1", "k1",
                                      usage_metrics={"tok": 10})
        assert UsageEvent.objects.count() == 0
        assert PricingPeriodCounter.objects.count() == 0
