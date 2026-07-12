"""P6a: run.limit_exceeded webhook fan-out from per-run/task cap kills, and the
start-gate honoring the customer-wide stop flag.

A per-run/per-task cap breach 429s the posting worker AND now emits a
run.limit_exceeded(scope="run") event so sibling/idle workers of that run tear
down (the reaper already emits for stale runs). The start-gate (RiskService)
blocks NEW runs for a flag-stopped owner in enforcing mode.
"""
import json

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from apps.billing.gating.models import RiskConfig
from apps.billing.gating.services.live_ledger_service import LiveLedgerService
from apps.billing.gating.services.risk_service import RiskService
from apps.billing.wallets.models import Wallet
from apps.platform.events.models import OutboxEvent
from apps.platform.runs.services import RunService
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey


def _tenant(mode="prepaid", enf="enforcing"):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf)


def _emitted(run_id, reason):
    return OutboxEvent.objects.filter(
        event_type="run.limit_exceeded", payload__run_id=str(run_id),
        payload__scope="run", payload__reason=reason).exists()


@pytest.mark.django_db
class TestRunLimitFanout:
    def setup_method(self):
        cache.clear()

    def test_per_run_cap_kill_emits_run_scoped_event(self):
        t = _tenant(enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1")
        _k, raw = TenantApiKey.create_key(t, label="t")
        run = RunService.create_run(tenant=t, customer=c, balance_snapshot_micros=0,
                                    cost_limit_micros=10_000_000, billing_owner_id=c.id)
        resp = Client().post(
            "/api/v1/metering/usage",
            data=json.dumps({"customer_id": str(c.id), "request_id": "r1",
                             "idempotency_key": "k1", "billed_cost_micros": 15_000_000,
                             "run_id": str(run.id)}),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {raw}")
        assert resp.status_code == 429
        assert resp.json()["reason"] == "cost_limit_exceeded"
        run.refresh_from_db()
        assert run.status == "killed"
        assert _emitted(run.id, "cost_limit_exceeded")

    def test_task_cap_kill_with_run_emits_run_scoped_event(self):
        t = _tenant(enf="enforcing")
        RiskConfig.objects.create(tenant=t, max_cost_per_task_micros=10_000_000)
        c = Customer.objects.create(tenant=t, external_id="c1")
        _k, raw = TenantApiKey.create_key(t, label="t")
        run = RunService.create_run(tenant=t, customer=c, balance_snapshot_micros=0,
                                    billing_owner_id=c.id)
        resp = Client().post(
            "/api/v1/metering/usage",
            data=json.dumps({"customer_id": str(c.id), "request_id": "r1",
                             "idempotency_key": "k1", "billed_cost_micros": 15_000_000,
                             "run_id": str(run.id), "tags": {"task": "t1"}}),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {raw}")
        assert resp.status_code == 429
        assert resp.json()["reason"] == "task_limit_exceeded"
        assert _emitted(run.id, "task_limit_exceeded")

    def test_runless_task_cap_emits_no_event(self):
        t = _tenant(enf="enforcing")
        RiskConfig.objects.create(tenant=t, max_cost_per_task_micros=10_000_000)
        c = Customer.objects.create(tenant=t, external_id="c1")
        _k, raw = TenantApiKey.create_key(t, label="t")
        resp = Client().post(
            "/api/v1/metering/usage",
            data=json.dumps({"customer_id": str(c.id), "request_id": "r1",
                             "idempotency_key": "k1", "billed_cost_micros": 15_000_000,
                             "tags": {"task": "t1"}}),  # no run_id
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {raw}")
        assert resp.status_code == 429
        assert not OutboxEvent.objects.filter(event_type="run.limit_exceeded").exists()

    def test_run_limit_exceeded_is_registered_for_delivery(self):
        from apps.platform.events.registry import handler_registry
        # P0 registered it; without registration the event is written but never
        # dispatched to webhooks.
        assert handler_registry.get_handlers("run.limit_exceeded")


@pytest.mark.django_db
class TestStartGateHonorsStopFlag:
    def setup_method(self):
        cache.clear()

    def test_blocks_new_run_when_flag_set_enforcing(self):
        t = _tenant(enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        LiveLedgerService.record_usage_debit(c.id, t, 6_000_000, now=timezone.now())  # crosses -> flag set
        res = RiskService.check(c, create_run=True)
        assert res["allowed"] is False
        assert res["reason"] == "customer_stopped"
        assert res["run_id"] is None

    def test_advisory_flag_does_not_block_start_gate(self):
        t = _tenant(enf="advisory")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        LiveLedgerService.record_usage_debit(c.id, t, 6_000_000, now=timezone.now())  # flag set (advisory)
        res = RiskService.check(c, create_run=True)
        assert res["allowed"] is True  # advisory never blocks at the gate

    def test_allowed_again_after_flag_cleared(self):
        t = _tenant(enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        LiveLedgerService.record_usage_debit(c.id, t, 6_000_000, now=timezone.now())
        assert RiskService.check(c, create_run=True)["allowed"] is False
        LiveLedgerService.credit(c.id, t, 10_000_000)  # recovery clears the flag
        assert RiskService.check(c, create_run=True)["allowed"] is True
