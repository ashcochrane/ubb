"""P7: flag-off cleanup (D17), live-vs-durable drift alert, enforcement_mode flip."""
import json
import logging

import pytest
from django.core.cache import cache
from django.test import Client

from apps.billing.gating.services.live_ledger_service import (
    LiveLedgerService, _client, _livebal_key, _stop_key,
)
from apps.billing.wallets.models import Wallet
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey


def _tenant(mode="prepaid", enf="enforcing"):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf)


@pytest.mark.django_db
class TestCleanupKeys:
    def setup_method(self):
        cache.clear()

    def test_clears_stop_and_balance_for_tenant_owners(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        _client().set(_livebal_key(c.id), 1_000_000)
        _client().set(_stop_key(c.id), "customer_wide_stop")
        LiveLedgerService.cleanup_keys(t)
        assert _client().get(_livebal_key(c.id)) is None
        assert _client().get(_stop_key(c.id)) is None

    def test_leaves_other_tenants_keys(self):
        t1 = _tenant()
        t2 = _tenant()
        c2 = Customer.objects.create(tenant=t2, external_id="c2")
        _client().set(_stop_key(c2.id), "customer_wide_stop")
        LiveLedgerService.cleanup_keys(t1)  # cleaning t1 must not touch t2's keys
        assert _client().get(_stop_key(c2.id)) is not None


@pytest.mark.django_db
class TestDriftAlert:
    def setup_method(self):
        cache.clear()

    def test_reconcile_prepaid_logs_drift_spike(self, caplog):
        t = _tenant(mode="prepaid", enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=0)  # durable 0
        _client().set(_livebal_key(c.id), 100_000_000)  # live $100 above durable
        with caplog.at_level(logging.ERROR, logger="ubb.billing"):
            LiveLedgerService.reconcile_prepaid(c.id, t)
        assert any(r.message == "live_ledger.drift_spike" for r in caplog.records)

    def test_no_drift_alert_when_aligned(self, caplog):
        t = _tenant(mode="prepaid", enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=1_000_000)
        _client().set(_livebal_key(c.id), 1_000_000)  # aligned
        with caplog.at_level(logging.ERROR, logger="ubb.billing"):
            LiveLedgerService.reconcile_prepaid(c.id, t)
        assert not any(r.message == "live_ledger.drift_spike" for r in caplog.records)


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
        resp = self._patch(raw, {"enforcement_mode": "advisory"})
        assert resp.status_code == 200
        assert resp.json()["enforcement_mode"] == "advisory"
        t.refresh_from_db()
        assert t.enforcement_mode == "advisory"

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
        _client().set(_stop_key(c.id), "customer_wide_stop")
        _k, raw = TenantApiKey.create_key(t, label="t")
        with django_capture_on_commit_callbacks(execute=True):
            resp = self._patch(raw, {"enforcement_mode": "off"})
        assert resp.status_code == 200
        assert _client().get(_stop_key(c.id)) is None  # cleanup_keys ran on the flip
