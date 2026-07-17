"""P8: end-to-end enforcement SEAM.

The one test that drives the WHOLE flag-gated Tier-2 pipeline through the real
endpoints under a SINGLE enforcement_mode flip, proving P0..P7 wire together on
the same flag/owner/counter (the divergent-flag class of bug would fail here):

  start-gate allows (P0 flag + RiskService)
   -> usage decrements the live counter (P2)
   -> a crossing event returns 200 stop=True and IS still charged (P3 + I3)
   -> the start-gate now BLOCKS a new task (P6a honors the flag)
   -> a top-up clears the flag via the credit hook (P2/P7)
   -> the start-gate allows again (recovery).

(The durable suspend/un-suspend is async — covered in test_p6b_suspend; the
task-limit fan-out in test_p6_fanout. This seam covers the synchronous spine.)
"""
import json

import pytest
from django.core.cache import cache
from django.test import Client

from apps.metering.usage.models import UsageEvent
from apps.billing.wallets.models import Wallet
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey


@pytest.mark.django_db
class TestEnforcementSeam:
    def setup_method(self):
        cache.clear()

    def test_full_customer_wide_stop_pipeline(self, django_capture_on_commit_callbacks):
        client = Client()
        t = Tenant.objects.create(name="Scouta", products=["metering", "billing"],
                                  billing_mode="prepaid", enforcement_mode="enforcing")
        _k, raw = TenantApiKey.create_key(t, label="t")
        hdr = {"content_type": "application/json", "HTTP_AUTHORIZATION": f"Bearer {raw}"}
        c = Customer.objects.create(tenant=t, external_id="jim")
        Wallet.objects.create(customer=c, balance_micros=10_000_000)  # $10; floor = -min_balance = 0

        def pre_check():
            return client.post("/api/v1/billing/pre-check",
                               data=json.dumps({"customer_id": str(c.id), "start_task": True}), **hdr)

        def record(key, billed, task_id):
            return client.post("/api/v1/metering/usage", data=json.dumps({
                "customer_id": str(c.id), "request_id": key, "idempotency_key": key,
                "billed_cost_micros": billed, "task_id": task_id}), **hdr)

        # 1. Start-gate allows a new task ($10 above floor).
        p1 = pre_check()
        assert p1.status_code == 200 and p1.json()["allowed"] is True
        task_id = p1.json()["task_id"]

        # 2. Usage under the floor -> no stop.
        assert record("k1", 4_000_000, task_id).json()["stop"] is False

        # 3. Crossing event (10 - 4 - 8 = -2M < floor) -> cooperative stop, and
        #    the breaching event IS still recorded + charged (I3, not rolled back).
        r2 = record("k2", 8_000_000, task_id).json()
        assert r2["stop"] is True
        assert r2["stop_reason"] == "customer_wide_stop"
        assert UsageEvent.objects.filter(tenant=t, customer=c, idempotency_key="k2").exists()

        # 4. Start-gate now BLOCKS a new task. #39: the winning stop transition
        #    durably suspends AT the crossing (the suspension fold), so the
        #    gate's status check answers first — the suspension-shaped refusal,
        #    not the flag-shaped customer_stopped (which now only surfaces when
        #    the flag exists without the suspension, e.g. a stale flag).
        p2 = pre_check()
        assert p2.json()["allowed"] is False
        assert p2.json()["reason"] == "insufficient_funds"
        c.refresh_from_db()
        assert c.status == "suspended"  # the fold landed synchronously

        # 5. Top-up recovers -> the credit hook (on_commit) clears the flag,
        #    un-suspends, and (#39) emits stop.cleared through the guard. The
        #    guard's write_event runs post-commit here, so its own dispatch
        #    on_commit fires immediately — patch the Celery task away.
        from unittest.mock import patch as _patch
        with _patch("apps.platform.events.tasks.process_single_event"):
            with django_capture_on_commit_callbacks(execute=True):
                cr = client.post("/api/v1/billing/credit", data=json.dumps({
                    "customer_id": "jim", "amount_micros": 20_000_000,
                    "source": "topup", "reference": "tp1",
                    "idempotency_key": "idem_tp1"}), **hdr)
        assert cr.status_code == 200
        from apps.platform.events.models import OutboxEvent
        cleared = OutboxEvent.objects.filter(event_type="stop.cleared")
        assert cleared.count() == 1  # the resume signal, once, episode 1
        assert cleared.get().payload["episode_seq"] == 1

        # 6. Start-gate ALLOWS again (recovery — the seam closes the loop).
        p3 = pre_check()
        assert p3.json()["allowed"] is True

    def test_off_tenant_pipeline_never_stops(self):
        # Control: the identical flow with enforcement_mode=off never stops or
        # blocks — proving the entire pipeline is gated by the single flag.
        client = Client()
        t = Tenant.objects.create(name="Off", products=["metering", "billing"],
                                  billing_mode="prepaid", enforcement_mode="off")
        _k, raw = TenantApiKey.create_key(t, label="t")
        hdr = {"content_type": "application/json", "HTTP_AUTHORIZATION": f"Bearer {raw}"}
        c = Customer.objects.create(tenant=t, external_id="jim")
        Wallet.objects.create(customer=c, balance_micros=10_000_000)
        p1 = client.post("/api/v1/billing/pre-check",
                         data=json.dumps({"customer_id": str(c.id), "start_task": True}), **hdr)
        task_id = p1.json()["task_id"]
        r = client.post("/api/v1/metering/usage", data=json.dumps({
            "customer_id": str(c.id), "request_id": "k1", "idempotency_key": "k1",
            "billed_cost_micros": 50_000_000, "task_id": task_id}), **hdr)  # way over balance
        assert r.json()["stop"] is False  # off => no stop verdict
        p2 = client.post("/api/v1/billing/pre-check",
                         data=json.dumps({"customer_id": str(c.id), "start_task": True}), **hdr)
        assert p2.json()["allowed"] is True  # off => never blocks on the flag
