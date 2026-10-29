"""Pin 8 (#42, spec §G/§L): enforcement mode is two-position.

The choices are two-position on every surface — `advisory` is retired, and the
config route refuses it; `off` is byte-for-byte pre-enforcement (Tier-1)
behavior — no counters, no signals, no tagging — while the Tier-1 baseline
(drawdown, zero-crossing early warning, level-based suspend) is untouched.

Before the cutover (#190) this module also drove `tenants/0019`'s data step,
which moved every stored `advisory` row to `off`; that step left with the
squashed chain, and what it left behind — the two-position choice set — is
pinned below.
"""
import json
import uuid
from dataclasses import asdict

import pytest
from django.core.cache import cache
from django.test import Client

from apps.billing.gating.models import StopSignalState
from apps.billing.gating.services.live_counter import Door
from apps.billing.handlers import handle_usage_recorded_billing
from apps.billing.wallets.models import Wallet
from apps.metering.pricing.tests._helpers import (
    a_rule_that_prices_what_it_measures, priced_at)
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import (
    CustomerStopCleared, CustomerStopped, UsageRecorded,
    WalletPolicySoftFloorCleared, WalletPolicySoftFloorCrossed)
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work import reasons
from apps.platform.tenants.tests._rails import activate_the_rail


def _tenant(mode="prepaid", enf="off"):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf)


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
class TestAdvisoryRetired:
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
        # A money-mode tenant needs the payment rail activated first (G27);
        # asked for here, by name, before the tenant is built.
        activate_the_rail()
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
        # 8,000,000 is what the tenant's rule charges for this event now (#365).
        a_rule_that_prices_what_it_measures(t)
        r = client.post("/api/v1/metering/usage", data=json.dumps({
            "customer_id": str(c.id), "idempotency_key": "k1",
            "measurements": priced_at(8_000_000)}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw}")
        assert r.status_code == 200
        body = r.json()
        assert body["stop"] is False and body["stop_reason"] is None
        ev = Posting.objects.get(tenant=t, idempotency_key="k1")
        assert ev.stop_context is None                            # no tagging
        assert Door.balance(c.id) is None                         # no counter
        assert Door.stop_reason(c.id) is None                     # no flag
        assert not StopSignalState.objects.filter(owner=c).exists()  # no ledger
        assert not OutboxEvent.objects.filter(event_type__in=[
            CustomerStopped.EVENT_TYPE, CustomerStopCleared.EVENT_TYPE,
            WalletPolicySoftFloorCrossed.EVENT_TYPE,
            WalletPolicySoftFloorCleared.EVENT_TYPE]).exists()  # no signals

    def test_tier1_baseline_survives_untouched(self):
        # The pre-enforcement reactions still run in off: durable drawdown,
        # the zero-crossing early warning, and the level-based baseline
        # suspend — none of them are enforcement-mode gated.
        t = _tenant(enf="off")
        c = Customer.objects.create(tenant=t, external_id="jim")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        handle_usage_recorded_billing(str(uuid.uuid4()), asdict(UsageRecorded(
            pricing_status_reason=None,
            tenant_id=t.id, customer_id=c.id,
            event_id=str(uuid.uuid4()), cost_micros=8_000_000)))
        w = Wallet.objects.get(customer=c)
        assert w.balance_micros == -3_000_000                     # billed
        c.refresh_from_db()
        assert c.status == "suspended"                            # baseline
        assert c.suspension_reason == reasons.HARD_FLOOR
        assert OutboxEvent.objects.filter(
            event_type="wallet.balance_overage").count() == 1    # early warning
        assert OutboxEvent.objects.filter(
            event_type="customer.suspended").count() == 1
        assert not OutboxEvent.objects.filter(event_type=CustomerStopped.EVENT_TYPE).exists()
        assert not StopSignalState.objects.filter(owner=c).exists()
