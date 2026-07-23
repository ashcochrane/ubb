"""Pin 8 (#42, spec §G/§L): enforcement mode is two-position.

The advisory→off migration lands; the choices are two-position on every
surface; `off` is byte-for-byte pre-enforcement (Tier-1) behavior — no
counters, no signals, no tagging — while the Tier-1 baseline (drawdown,
zero-crossing early warning, level-based suspend) is untouched.
"""
import json
import uuid
from importlib import import_module

import pytest
from django.core.cache import cache
from django.test import Client

from apps.billing.gating.models import StopSignalState
from apps.billing.gating.services.live_counter import Door
from apps.billing.handlers import handle_usage_recorded_billing
from apps.billing.wallets.models import Wallet
from apps.metering.usage.models import UsageEvent
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant, TenantApiKey


def _tenant(mode="prepaid", enf="off"):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf)


@pytest.mark.django_db
class TestAdvisoryRetired:
    def test_migration_maps_advisory_to_off(self):
        from django.apps import apps as live_apps
        t = _tenant(enf="enforcing")
        # Seed the retired value the way a pre-migration row holds it
        # (queryset update — the model choices no longer admit it).
        Tenant.objects.filter(id=t.id).update(enforcement_mode="advisory")
        mig = import_module(
            "apps.platform.tenants.migrations.0019_two_position_enforcement_mode")
        mig.advisory_to_off(live_apps, None)
        t.refresh_from_db()
        assert t.enforcement_mode == "off"

    def test_migration_leaves_both_live_positions_alone(self):
        from django.apps import apps as live_apps
        on = _tenant(enf="enforcing")
        off = _tenant(enf="off")
        mig = import_module(
            "apps.platform.tenants.migrations.0019_two_position_enforcement_mode")
        mig.advisory_to_off(live_apps, None)
        on.refresh_from_db()
        off.refresh_from_db()
        assert on.enforcement_mode == "enforcing"
        assert off.enforcement_mode == "off"

    def test_choices_are_two_position(self):
        from apps.platform.tenants.models import ENFORCEMENT_MODE_CHOICES
        assert [c[0] for c in ENFORCEMENT_MODE_CHOICES] == ["off", "enforcing"]

    def test_patch_advisory_refused_422(self):
        t = _tenant(enf="off")
        _k, raw = TenantApiKey.create_key(t, label="t")
        resp = Client().patch("/api/v1/tenant/config",
                              data=json.dumps({"enforcement_mode": "advisory"}),
                              content_type="application/json",
                              HTTP_AUTHORIZATION=f"Bearer {raw}")
        assert resp.status_code == 422
        t.refresh_from_db()
        assert t.enforcement_mode == "off"  # unchanged


@pytest.mark.django_db
class TestOffIsByteForBytePreEnforcement:
    def setup_method(self):
        cache.clear()

    def test_floor_crossing_leaves_no_enforcement_trace(self):
        # A crossing that would fire the whole suite in enforcing leaves
        # NOTHING in off: no live counter, no stop flag, no signal ledger
        # row, no stop/soft-floor events, no stop-context tag — while the
        # event itself lands and bills (Tier-1 kept).
        client = Client()
        t = _tenant(enf="off")
        _k, raw = TenantApiKey.create_key(t, label="t")
        c = Customer.objects.create(tenant=t, external_id="jim")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        r = client.post("/api/v1/metering/usage", data=json.dumps({
            "customer_id": str(c.id), "request_id": "k1", "idempotency_key": "k1",
            "billed_cost_micros": 8_000_000}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw}")
        assert r.status_code == 200
        body = r.json()
        assert body["stop"] is False and body["stop_reason"] is None
        ev = UsageEvent.objects.get(tenant=t, idempotency_key="k1")
        assert ev.stop_context is None                            # no tagging
        assert Door.balance(c.id) is None                         # no counter
        assert Door.stop_reason(c.id) is None                     # no flag
        assert not StopSignalState.objects.filter(owner=c).exists()  # no ledger
        assert not OutboxEvent.objects.filter(event_type__in=[
            "stop.fired", "stop.cleared", "soft_floor.crossed",
            "soft_floor.cleared"]).exists()                       # no signals

    def test_tier1_baseline_survives_untouched(self):
        # The pre-enforcement reactions still run in off: durable drawdown,
        # the zero-crossing early warning, and the level-based baseline
        # suspend — none of them are enforcement-mode gated.
        t = _tenant(enf="off")
        c = Customer.objects.create(tenant=t, external_id="jim")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        handle_usage_recorded_billing(str(uuid.uuid4()), {
            "tenant_id": str(t.id), "customer_id": str(c.id),
            "event_id": str(uuid.uuid4()), "cost_micros": 8_000_000})
        w = Wallet.objects.get(customer=c)
        assert w.balance_micros == -3_000_000                     # billed
        c.refresh_from_db()
        assert c.status == "suspended"                            # baseline
        assert c.suspension_reason == "min_balance_exceeded"
        assert OutboxEvent.objects.filter(
            event_type="billing.balance_overage").count() == 1    # early warning
        assert OutboxEvent.objects.filter(
            event_type="billing.customer_suspended").count() == 1
        assert not OutboxEvent.objects.filter(event_type="stop.fired").exists()
        assert not StopSignalState.objects.filter(owner=c).exists()
