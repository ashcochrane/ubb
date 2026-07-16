"""P6a: task.limit_exceeded fan-out from the endpoint/settle kill flow, and
the start-gate honoring the customer-wide stop flag.

One-rule (#37): a per-task limit crossing never rejects the usage report —
the tipping event answers HTTP 200, lands, and bills; the server runs the
idempotent kill flow (TaskService.kill_and_announce) which emits
task.limit_exceeded exactly once on the winning active->killed transition so
sibling/idle workers tear down. The start-gate (RiskService) still blocks NEW
tasks for a flag-stopped owner in enforcing mode.
"""
import json

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from apps.billing.gating.services.live_ledger_service import LiveLedgerService
from apps.billing.gating.services.risk_service import RiskService
from apps.billing.wallets.models import Wallet
from apps.platform.events.models import OutboxEvent
from apps.platform.tasks.services import TaskService
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey


def _tenant(mode="prepaid", enf="enforcing"):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf)


def _limit_events(task_id):
    return OutboxEvent.objects.filter(
        event_type="task.limit_exceeded", payload__task_id=str(task_id))


@pytest.mark.django_db
class TestTaskLimitFanout:
    def setup_method(self):
        cache.clear()

    def test_task_limit_crossing_emits_task_event_exactly_once(self):
        t = _tenant(enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=100_000_000)
        _k, raw = TenantApiKey.create_key(t, label="t")
        task = TaskService.create_task(
            tenant=t, customer=c, balance_snapshot_micros=100_000_000,
            provider_cost_limit_micros=10_000_000, billing_owner_id=c.id)

        def record(key, provider):
            return Client().post(
                "/api/v1/metering/usage",
                data=json.dumps({"customer_id": str(c.id), "request_id": key,
                                 "idempotency_key": key,
                                 "provider_cost_micros": provider,
                                 "billed_cost_micros": provider,
                                 "task_id": str(task.id)}),
                content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {raw}")

        # The crossing event answers 200 (one-rule: never a 429), the server
        # kills the task, and the fan-out event fires exactly once.
        resp = record("k1", 15_000_000)
        assert resp.status_code == 200
        body = resp.json()
        assert body["stop"] is True
        assert body["stop_reason"] == "task_limit"
        assert body["stop_scope"] == "task"
        task.refresh_from_db()
        assert task.status == "killed"
        assert _limit_events(task.id).count() == 1
        payload = _limit_events(task.id).get().payload
        assert payload["reason"] == "task_limit"
        assert "scope" not in payload

        # A late event on the killed task still lands (200) but never
        # re-announces — the kill flow is idempotent.
        resp = record("k2", 1_000_000)
        assert resp.status_code == 200
        assert resp.json()["stop_reason"] == "task_not_active"
        assert _limit_events(task.id).count() == 1

    def test_task_limit_exceeded_is_registered_for_delivery(self):
        from apps.platform.events.registry import handler_registry
        # Without registration the event is written but never dispatched to
        # webhooks; the run-era event type is gone from the registry.
        assert handler_registry.get_handlers("task.limit_exceeded")
        assert handler_registry.get_handlers("run.limit_exceeded") == []


@pytest.mark.django_db
class TestStartGateHonorsStopFlag:
    def setup_method(self):
        cache.clear()

    def test_blocks_new_task_when_flag_set_enforcing(self):
        t = _tenant(enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        LiveLedgerService.record_usage_debit(c.id, t, 6_000_000, now=timezone.now())  # crosses -> flag set
        res = RiskService.check(c, create_task=True)
        assert res["allowed"] is False
        assert res["reason"] == "customer_stopped"
        assert res["task_id"] is None

    def test_advisory_flag_does_not_block_start_gate(self):
        t = _tenant(enf="advisory")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        LiveLedgerService.record_usage_debit(c.id, t, 6_000_000, now=timezone.now())  # flag set (advisory)
        res = RiskService.check(c, create_task=True)
        assert res["allowed"] is True  # advisory never blocks at the gate

    def test_allowed_again_after_flag_cleared(self):
        t = _tenant(enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        LiveLedgerService.record_usage_debit(c.id, t, 6_000_000, now=timezone.now())
        assert RiskService.check(c, create_task=True)["allowed"] is False
        LiveLedgerService.credit(c.id, t, 10_000_000)  # recovery clears the flag
        assert RiskService.check(c, create_task=True)["allowed"] is True
