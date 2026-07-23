"""P7: flag-off cleanup (D17), live-vs-durable drift alert, enforcement_mode flip."""
import json
import logging

import pytest
from django.core.cache import cache
from django.test import Client

from apps.billing.gating.models import StopSignalState
from apps.billing.gating.services.live_counter import Door, LiveCounter
from apps.billing.gating.services.stop_signal_service import (
    CLEAR_ENFORCEMENT_MODE_TRANSITION,
    STATE_CLEARED,
    StopSignalService,
)
from apps.billing.wallets.models import Wallet
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant, TenantApiKey


def _tenant(mode="prepaid", enf="enforcing"):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf)


@pytest.mark.django_db
class TestCleanup:
    def setup_method(self):
        cache.clear()

    def test_clears_stop_and_balance_for_tenant_owners(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        Door.set_balance(c.id, 1_000_000)
        Door.plant_stop(c.id, "customer_wide_stop", ttl=False)
        LiveCounter.cleanup(t)
        assert Door.balance(c.id) is None
        assert Door.stop_reason(c.id) is None

    def test_leaves_other_tenants_keys(self):
        t1 = _tenant()
        t2 = _tenant()
        c2 = Customer.objects.create(tenant=t2, external_id="c2")
        Door.plant_stop(c2.id, "customer_wide_stop", ttl=False)
        LiveCounter.cleanup(t1)  # cleaning t1 must not touch t2's keys
        assert Door.stop_reason(c2.id) is not None

    def test_silent_close_is_bulk_non_emitting_and_preserves_episode_seq(self):
        # The D5 trap pin (#111): cleanup's ledger leg is a BULK,
        # NON-EMITTING close — a config flip is not a re-cross, so no
        # stop.cleared rides out, and episode_seq is preserved so episode
        # ids never restart or collide. A rewrite as a loop of drive_clear
        # calls would emit per row and fail here.
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=-1_000_000)
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        StopSignalService.drive_clear(c.id, t, reason="balance_recovered")
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        row = StopSignalState.objects.get(owner=c)
        assert row.episode_seq == 2  # a real history, not a fresh row
        cleared_before = OutboxEvent.objects.filter(
            event_type="stop.cleared").count()

        LiveCounter.cleanup(t)

        row.refresh_from_db()
        assert row.state == STATE_CLEARED
        assert row.reason == CLEAR_ENFORCEMENT_MODE_TRANSITION
        assert row.episode_seq == 2  # preserved, never reset
        # Non-emitting: the close itself put NOTHING on the wire.
        assert OutboxEvent.objects.filter(
            event_type="stop.cleared").count() == cleared_before
        # Ids never restart: the first real crossing after re-enable opens
        # episode 3, not a colliding episode 1.
        assert StopSignalService.drive_stop(
            c.id, t, reason="customer_wide_stop") == 3


@pytest.mark.django_db
class TestDriftAlert:
    def setup_method(self):
        cache.clear()

    def test_reconcile_prepaid_logs_drift_spike(self, caplog):
        t = _tenant(mode="prepaid", enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=0)  # durable 0
        Door.set_balance(c.id, 100_000_000)  # live $100 above durable
        with caplog.at_level(logging.ERROR, logger="ubb.billing"):
            LiveCounter.reconcile(c.id, t)
        assert any(r.message == "live_counter.drift_spike" for r in caplog.records)

    def test_no_drift_alert_when_aligned(self, caplog):
        t = _tenant(mode="prepaid", enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=1_000_000)
        Door.set_balance(c.id, 1_000_000)  # aligned
        with caplog.at_level(logging.ERROR, logger="ubb.billing"):
            LiveCounter.reconcile(c.id, t)
        assert not any(r.message == "live_counter.drift_spike" for r in caplog.records)


@pytest.mark.django_db
class TestEnforcementModeFlip:
    def setup_method(self):
        cache.clear()

    def _patch(self, raw, body):
        return Client().patch("/api/v1/tenant/config", data=json.dumps(body),
                              content_type="application/json",
                              HTTP_AUTHORIZATION=f"Bearer {raw}")

    def test_patch_sets_mode(self):
        t = _tenant(enf="off")
        _k, raw = TenantApiKey.create_key(t, label="t")
        resp = self._patch(raw, {"enforcement_mode": "enforcing"})
        assert resp.status_code == 200
        assert resp.json()["enforcement_mode"] == "enforcing"
        t.refresh_from_db()
        assert t.enforcement_mode == "enforcing"

    def test_patch_invalid_mode_422(self):
        t = _tenant(enf="off")
        _k, raw = TenantApiKey.create_key(t, label="t")
        resp = self._patch(raw, {"enforcement_mode": "bogus"})
        assert resp.status_code == 422
        t.refresh_from_db()
        assert t.enforcement_mode == "off"  # unchanged

    def test_flip_clears_stale_keys(self, django_capture_on_commit_callbacks):
        t = _tenant(enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Door.plant_stop(c.id, "customer_wide_stop", ttl=False)
        _k, raw = TenantApiKey.create_key(t, label="t")
        with django_capture_on_commit_callbacks(execute=True):
            resp = self._patch(raw, {"enforcement_mode": "off"})
        assert resp.status_code == 200
        assert Door.stop_reason(c.id) is None  # cleanup ran on the flip
