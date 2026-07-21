"""F4.2 caller timestamps: bounds matrix, historical pricing, closed-period
guard, dirty-period markers, outbox payload."""
import json
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.utils import timezone

from apps.billing.invoicing.models import CustomerUsageInvoice
from apps.metering.pricing.models import Rate
from apps.metering.pricing.tests._helpers import rate_in_default_book
from apps.metering.usage.models import BackfillDirtyPeriod, UsageEvent
from apps.metering.usage.services.usage_service import (
    EffectiveAtError, UsageService, validate_effective_at,
)
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant
from core.time_windows import month_bounds


def _setup(**tenant_kwargs):
    tenant = Tenant.objects.create(
        name="T", products=["metering", "billing"], **tenant_kwargs)
    customer = Customer.objects.create(tenant=tenant, external_id="c1")
    return tenant, customer


def _prior_month_eff():
    """An aware datetime in the PRIOR calendar month, guaranteed inside the
    default 34-day window (current month start − 2 days ≤ 33 days back)."""
    now = timezone.now()
    cur_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return cur_start - timedelta(days=2)


@pytest.mark.django_db
class TestEffectiveAtBounds:
    def test_four_minutes_ahead_accepted_lands_at_given_timestamp(self):
        t, c = _setup()
        eff = timezone.now() + timedelta(minutes=4)
        r = UsageService.record_usage(t, c, "r1", "k1",
                                      provider_cost_micros=10, effective_at=eff)
        event = UsageEvent.objects.get(id=r["event_id"])
        assert event.effective_at == eff

    def test_six_minutes_ahead_rejected(self):
        t, c = _setup()
        with pytest.raises(EffectiveAtError) as exc:
            UsageService.record_usage(t, c, "r1", "k1", provider_cost_micros=10,
                                      effective_at=timezone.now() + timedelta(minutes=6))
        assert exc.value.code == "effective_at_in_future"
        assert UsageEvent.objects.count() == 0

    def test_default_window_33_days_accepted_35_rejected(self):
        t, c = _setup()
        ok = UsageService.record_usage(t, c, "r1", "k1", provider_cost_micros=10,
                                       effective_at=timezone.now() - timedelta(days=33))
        assert UsageEvent.objects.filter(id=ok["event_id"]).exists()
        with pytest.raises(EffectiveAtError) as exc:
            UsageService.record_usage(t, c, "r2", "k2", provider_cost_micros=10,
                                      effective_at=timezone.now() - timedelta(days=35))
        assert exc.value.code == "effective_at_too_old"

    def test_per_tenant_window_seven_days(self):
        t, c = _setup(backfill_window_days=7)
        with pytest.raises(EffectiveAtError) as exc:
            UsageService.record_usage(t, c, "r1", "k1", provider_cost_micros=10,
                                      effective_at=timezone.now() - timedelta(days=8))
        assert exc.value.code == "effective_at_too_old"
        r = UsageService.record_usage(t, c, "r2", "k2", provider_cost_micros=10,
                                      effective_at=timezone.now() - timedelta(days=6))
        assert UsageEvent.objects.filter(id=r["event_id"]).exists()

    def test_window_zero_rejects_any_backdated(self):
        t, c = _setup(backfill_window_days=0)
        with pytest.raises(EffectiveAtError) as exc:
            UsageService.record_usage(t, c, "r1", "k1", provider_cost_micros=10,
                                      effective_at=timezone.now() - timedelta(hours=1))
        assert exc.value.code == "effective_at_too_old"

    def test_naive_rejected(self):
        t, c = _setup()
        with pytest.raises(EffectiveAtError) as exc:
            UsageService.record_usage(t, c, "r1", "k1", provider_cost_micros=10,
                                      effective_at=timezone.now().replace(tzinfo=None))
        assert exc.value.code == "effective_at_naive"

    def test_omitted_defaults_to_now(self):
        """Regression: the default path must be identical to the old
        auto_now_add behavior (effective_at ≈ created_at ≈ now)."""
        t, c = _setup()
        before = timezone.now()
        r = UsageService.record_usage(t, c, "r1", "k1", provider_cost_micros=10)
        event = UsageEvent.objects.get(id=r["event_id"])
        assert before <= event.effective_at <= timezone.now()
        assert abs((event.effective_at - event.created_at).total_seconds()) < 5

    def test_clean_bounds_window_0_to_60(self):
        with pytest.raises(ValidationError):
            Tenant.objects.create(name="Bad", backfill_window_days=61)
        t = Tenant.objects.create(name="Ok", backfill_window_days=0)
        assert t.backfill_window_days == 0

    def test_replay_wins_before_validation(self):
        """A replayed idempotency key returns the original event even when the
        replayed effective_at would now be rejected — batch-retry safety."""
        t, c = _setup()
        r1 = UsageService.record_usage(t, c, "r1", "dup", provider_cost_micros=10)
        r2 = UsageService.record_usage(t, c, "r1", "dup", provider_cost_micros=10,
                                       effective_at=timezone.now() - timedelta(days=300))
        assert r2["event_id"] == r1["event_id"]
        assert UsageEvent.objects.count() == 1


@pytest.mark.django_db
class TestEffectiveAtEndpoint:
    def _post(self, payload, tenant_kwargs=None):
        from apps.platform.tenants.models import TenantApiKey
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  **(tenant_kwargs or {}))
        _, raw_key = TenantApiKey.create_key(t, label="test")
        c = Customer.objects.create(tenant=t, external_id="cust1")
        resp = Client().post(
            "/api/v1/metering/usage",
            data=json.dumps({"customer_id": str(c.id), **payload}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}")
        return resp

    def test_naive_string_422_with_typed_code(self):
        resp = self._post({"request_id": "r1", "idempotency_key": "k1",
                           "provider_cost_micros": 10,
                           "effective_at": "2026-06-01T12:00:00"})
        assert resp.status_code == 422
        assert resp["Content-Type"] == "application/problem+json"
        body = resp.json()
        assert body["code"] == "effective_at_naive"
        assert "detail" in body

    def test_in_future_422_with_typed_code(self):
        eff = (timezone.now() + timedelta(minutes=10)).isoformat()
        resp = self._post({"request_id": "r1", "idempotency_key": "k1",
                           "provider_cost_micros": 10, "effective_at": eff})
        assert resp.status_code == 422
        assert resp.json()["code"] == "effective_at_in_future"

    def test_too_old_422_with_typed_code(self):
        eff = (timezone.now() - timedelta(days=40)).isoformat()
        resp = self._post({"request_id": "r1", "idempotency_key": "k1",
                           "provider_cost_micros": 10, "effective_at": eff})
        assert resp.status_code == 422
        assert resp.json()["code"] == "effective_at_too_old"

    def test_valid_effective_at_200(self):
        eff = (timezone.now() - timedelta(days=3)).isoformat()
        resp = self._post({"request_id": "r1", "idempotency_key": "k1",
                           "provider_cost_micros": 10, "effective_at": eff})
        assert resp.status_code == 200


@pytest.mark.django_db
class TestHistoricalPricing:
    def test_backdated_event_prices_on_superseded_card_version(self):
        """as_of threading proof: v1 (10 micros/unit) superseded by v2 (50)
        ten days ago; an event effective in the v1 era prices on v1 and the
        provenance pins v1's rate_card_id."""
        t, c = _setup()
        now = timezone.now()
        v1 = rate_in_default_book(t, card_type="price", metric_name="tok",
            pricing_model="per_unit", rate_per_unit_micros=10, unit_quantity=1)
        Rate.objects.filter(id=v1.id).update(
            valid_from=now - timedelta(days=40), valid_to=now - timedelta(days=10))
        v2 = rate_in_default_book(t, card_type="price", metric_name="tok", lineage_id=v1.lineage_id,
            pricing_model="per_unit", rate_per_unit_micros=50, unit_quantity=1)
        Rate.objects.filter(id=v2.id).update(valid_from=now - timedelta(days=10))

        r_old = UsageService.record_usage(
            t, c, "r1", "k1", usage_metrics={"tok": 100},
            effective_at=now - timedelta(days=20))
        assert r_old["billed_cost_micros"] == 1_000  # 100 @ v1's 10
        entry = [m for m in r_old["pricing_provenance"]["metrics"]
                 if m["card_type"] == "price"][0]
        assert entry["rate_card_id"] == str(v1.id)

        r_new = UsageService.record_usage(
            t, c, "r2", "k2", usage_metrics={"tok": 100})
        assert r_new["billed_cost_micros"] == 5_000  # 100 @ v2's 50


@pytest.mark.django_db
class TestClosedPeriodGuard:
    @pytest.mark.parametrize("status,push_phase,stripe_invoice_id,line_snapshot", [
        ("pushed", "", "", []),
        ("pushing", "", "", []),
        ("skipped", "", "", []),
        ("failed_permanent", "", "", []),
        ("pending", "invoice_created", "", []),  # pointer phase, status not yet flipped
        ("pending", "", "in_123", []),           # Stripe pointer persisted
        # Snapshot-frozen rows whose status/phase/pointer all read "untouched"
        # — the F4.2-review hole. Lines freeze at FIRST CLAIM (Phase 1), so:
        # a Phase-2 failure BEFORE Invoice.create leaves status="failed",
        # push_phase="", stripe_invoice_id="" with the lines already frozen;
        ("failed", "", "", [["", 5_000_000]]),
        # and a reclaimed pending row (mid-claim window) reads the same way.
        ("pending", "", "", [["", 5_000_000]]),
    ])
    def test_touched_owner_period_rejects_backfill(self, status, push_phase,
                                                   stripe_invoice_id, line_snapshot):
        t, c = _setup(billing_mode="postpaid")
        eff = _prior_month_eff()
        period_start, period_end = month_bounds(eff)
        CustomerUsageInvoice.objects.create(
            tenant=t, customer=c, period_start=period_start, period_end=period_end,
            status=status, push_phase=push_phase, stripe_invoice_id=stripe_invoice_id,
            line_snapshot=line_snapshot)
        with pytest.raises(EffectiveAtError) as exc:
            UsageService.record_usage(t, c, "r1", "k1",
                                      provider_cost_micros=10, effective_at=eff)
        assert exc.value.code == "billing_period_closed"
        assert UsageEvent.objects.count() == 0

    def test_genuinely_fresh_pending_empty_snapshot_accepts(self):
        """A pending row with NO frozen snapshot (and no phase/pointer) is the
        only invoice state that leaves the period open."""
        t, c = _setup(billing_mode="postpaid")
        eff = _prior_month_eff()
        period_start, period_end = month_bounds(eff)
        CustomerUsageInvoice.objects.create(
            tenant=t, customer=c, period_start=period_start, period_end=period_end,
            status="pending")  # line_snapshot defaults to []
        r = UsageService.record_usage(t, c, "r1", "k1",
                                      provider_cost_micros=10, effective_at=eff)
        assert UsageEvent.objects.filter(id=r["event_id"]).exists()

    def test_untouched_pending_row_accepts_and_push_reaggregates(self):
        """A pending row that never touched Stripe does NOT close the period,
        and a subsequent push re-aggregates INCLUDING the backfilled event."""
        from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService
        t, c = _setup(billing_mode="postpaid")
        eff = _prior_month_eff()
        period_start, period_end = month_bounds(eff)
        rec = CustomerUsageInvoice.objects.create(
            tenant=t, customer=c, period_start=period_start, period_end=period_end,
            status="pending")
        r = UsageService.record_usage(t, c, "r1", "k1",
                                      billed_cost_micros=7_000_000, effective_at=eff)
        assert UsageEvent.objects.filter(id=r["event_id"]).exists()
        # No stripe_customer_id: Phase 1 aggregates (proving the re-aggregation
        # picks the backfill up) then skips before any Stripe call.
        result = PostpaidUsageService.push_customer_period(
            t, c, period_start, period_end)
        assert result.id == rec.id
        assert result.total_billed_micros == 7_000_000
        assert result.status == "skipped" and result.skip_reason == "no_stripe_customer"

    def test_seat_backfill_into_owners_closed_period_rejected(self):
        """The guard keys on resolve_billing_owner: a pooled seat backfilling
        into the BUSINESS's closed period is rejected."""
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="postpaid")
        biz = Customer.objects.create(tenant=t, external_id="biz",
                                      account_type="business",
                                      billing_topology="pooled")
        seat = Customer.objects.create(tenant=t, external_id="seat-1",
                                       account_type="seat", parent=biz)
        eff = _prior_month_eff()
        period_start, period_end = month_bounds(eff)
        CustomerUsageInvoice.objects.create(
            tenant=t, customer=biz, period_start=period_start, period_end=period_end,
            status="pushed", stripe_invoice_id="in_42")
        with pytest.raises(EffectiveAtError) as exc:
            UsageService.record_usage(t, seat, "r1", "k1",
                                      provider_cost_micros=10, effective_at=eff)
        assert exc.value.code == "billing_period_closed"

    def test_validate_effective_at_unit(self):
        """Direct unit coverage for the validator's signature."""
        t, c = _setup()
        now = timezone.now()
        # No invoice rows at all: open period, no exception.
        validate_effective_at(t, c.id, now - timedelta(days=5), now)


@pytest.mark.django_db
class TestBackfillDirtyMarkers:
    def test_prior_month_backfill_writes_marker_once(self):
        t, c = _setup()
        eff = _prior_month_eff()
        period_start, _ = month_bounds(eff)
        UsageService.record_usage(t, c, "r1", "k1",
                                  provider_cost_micros=10, effective_at=eff)
        marker = BackfillDirtyPeriod.objects.get(tenant=t, customer=c)
        assert marker.period_start == period_start
        # Second backfill into the same period: unique swallowed, still 1 marker.
        UsageService.record_usage(t, c, "r2", "k2",
                                  provider_cost_micros=10, effective_at=eff)
        assert BackfillDirtyPeriod.objects.count() == 1

    def test_same_month_backdated_event_writes_no_marker(self):
        t, c = _setup()
        eff = timezone.now() - timedelta(minutes=30)
        UsageService.record_usage(t, c, "r1", "k1",
                                  provider_cost_micros=10, effective_at=eff)
        assert BackfillDirtyPeriod.objects.count() == 0

    def test_marker_unique_constraint(self):
        from django.db import IntegrityError, transaction
        t, c = _setup()
        period_start, _ = month_bounds(_prior_month_eff())
        BackfillDirtyPeriod.objects.create(tenant=t, customer=c, period_start=period_start)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                BackfillDirtyPeriod.objects.create(
                    tenant=t, customer=c, period_start=period_start)


@pytest.mark.django_db
class TestUsageRecordedPayload:
    def test_payload_carries_utc_effective_at(self):
        import datetime as dt
        t, c = _setup()
        # Offset timezone: payload must be normalized to UTC.
        eff = (timezone.now() - timedelta(days=1)).astimezone(
            dt.timezone(dt.timedelta(hours=5)))
        r = UsageService.record_usage(t, c, "r1", "k1",
                                      provider_cost_micros=10, effective_at=eff)
        evt = OutboxEvent.objects.get(event_type="usage.recorded", tenant_id=t.id)
        payload_eff = dt.datetime.fromisoformat(evt.payload["effective_at"])
        assert payload_eff.utcoffset() == dt.timedelta(0)
        assert payload_eff == eff  # same instant
        event = UsageEvent.objects.get(id=r["event_id"])
        assert event.effective_at == eff

    def test_payload_present_on_default_path_too(self):
        import datetime as dt
        t, c = _setup()
        UsageService.record_usage(t, c, "r1", "k1", provider_cost_micros=10)
        evt = OutboxEvent.objects.get(event_type="usage.recorded", tenant_id=t.id)
        assert dt.datetime.fromisoformat(evt.payload["effective_at"])

    def test_schema_default_keeps_legacy_payloads_valid(self):
        from apps.platform.events.schemas import UsageRecorded
        legacy = UsageRecorded(tenant_id="t", customer_id="c", event_id="e",
                               cost_micros=5)
        assert legacy.effective_at == ""
