"""P4 (D12): per-task cost cap + per-run cap regression + 429 reason taxonomy.

The per-task cap is an ENFORCING-only hard stop: cumulative billed spend across
all runs sharing a task_id, capped per calendar month. A breach raises
HardStopExceeded(reason=task_limit_exceeded) so the endpoint rejects the event
(429) and kills the run (if any). The per-run cap (RunService.accumulate_cost)
is baseline and billing-mode-agnostic.
"""
import json

import pytest
from django.core.cache import cache
from django.test import Client

from apps.billing.gating.models import RiskConfig
from apps.billing.gating.services.live_ledger_service import LiveLedgerService
from apps.platform.customers.models import Customer
from apps.platform.runs.services import HardStopExceeded, RunService
from apps.metering.usage.models import UsageEvent
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.tenants.models import Tenant, TenantApiKey
from unittest.mock import patch


def _tenant(mode="prepaid", enf="enforcing"):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf)


@pytest.mark.django_db
class TestTaskCapService:
    def setup_method(self):
        cache.clear()

    def test_exact_cap_semantics(self):
        # cap 50M: a 30M event counts; a second 30M (would be 60M) is rejected
        # and NOT counted; a later 10M (30M+10M=40M) is allowed.
        t = _tenant()
        RiskConfig.objects.create(tenant=t, max_cost_per_task_micros=50_000_000)
        c = Customer.objects.create(tenant=t, external_id="c1")
        LiveLedgerService.check_task_cost(c.id, t, "t1", 30_000_000)
        with pytest.raises(HardStopExceeded) as ei:
            LiveLedgerService.check_task_cost(c.id, t, "t1", 30_000_000)
        assert ei.value.reason == "task_limit_exceeded"
        assert ei.value.total_cost_micros == 60_000_000  # the would-be total
        LiveLedgerService.check_task_cost(c.id, t, "t1", 10_000_000)  # 40M, allowed

    def test_no_op_when_advisory(self):
        t = _tenant(enf="advisory")
        RiskConfig.objects.create(tenant=t, max_cost_per_task_micros=50_000_000)
        c = Customer.objects.create(tenant=t, external_id="c1")
        LiveLedgerService.check_task_cost(c.id, t, "t1", 60_000_000)  # no raise (advisory)

    def test_no_op_when_no_cap_configured(self):
        t = _tenant()  # no RiskConfig
        c = Customer.objects.create(tenant=t, external_id="c1")
        LiveLedgerService.check_task_cost(c.id, t, "t1", 999_000_000)  # no raise

    def test_no_op_when_no_task_id(self):
        t = _tenant()
        RiskConfig.objects.create(tenant=t, max_cost_per_task_micros=50_000_000)
        c = Customer.objects.create(tenant=t, external_id="c1")
        LiveLedgerService.check_task_cost(c.id, t, "", 60_000_000)  # no task -> no-op

    def test_distinct_tasks_have_independent_caps(self):
        t = _tenant()
        RiskConfig.objects.create(tenant=t, max_cost_per_task_micros=50_000_000)
        c = Customer.objects.create(tenant=t, external_id="c1")
        LiveLedgerService.check_task_cost(c.id, t, "t1", 40_000_000)
        LiveLedgerService.check_task_cost(c.id, t, "t2", 40_000_000)  # separate task, fine


@pytest.mark.django_db
class TestCapsViaRecordUsage:
    def setup_method(self):
        cache.clear()

    @patch("apps.platform.events.tasks.process_single_event")
    def test_per_run_cap_fires_in_postpaid(self, _m):
        # Baseline per-run cap is mode-agnostic AND independent of enforcement_mode.
        t = _tenant(mode="postpaid", enf="off")
        c = Customer.objects.create(tenant=t, external_id="c1")
        run = RunService.create_run(tenant=t, customer=c, balance_snapshot_micros=0,
                                    cost_limit_micros=15_000_000)
        with pytest.raises(HardStopExceeded) as ei:
            UsageService.record_usage(tenant=t, customer=c, request_id="r1",
                                      idempotency_key="k1", billed_cost_micros=20_000_000,
                                      run_id=run.id)
        assert ei.value.reason == "cost_limit_exceeded"

    @patch("apps.platform.events.tasks.process_single_event")
    def test_task_cap_runless_raises_and_event_rolls_back(self, _m):
        t = _tenant(enf="enforcing")
        RiskConfig.objects.create(tenant=t, max_cost_per_task_micros=50_000_000)
        c = Customer.objects.create(tenant=t, external_id="c1")
        with pytest.raises(HardStopExceeded) as ei:
            UsageService.record_usage(tenant=t, customer=c, request_id="r1",
                                      idempotency_key="k1", billed_cost_micros=60_000_000,
                                      tags={"task": "t1"})
        assert ei.value.reason == "task_limit_exceeded"
        # The breaching event is REJECTED (rolled back) — not recorded/charged.
        assert not UsageEvent.objects.filter(tenant=t, customer=c, idempotency_key="k1").exists()


@pytest.mark.django_db
class TestTaskCapEndpoint:
    def setup_method(self):
        cache.clear()

    def test_runless_task_breach_returns_429_no_crash(self):
        # The run-less task breach must NOT call kill_run(None) (would 500).
        t = _tenant(enf="enforcing")
        RiskConfig.objects.create(tenant=t, max_cost_per_task_micros=50_000_000)
        c = Customer.objects.create(tenant=t, external_id="c1")
        _k, raw = TenantApiKey.create_key(t, label="t")
        resp = Client().post(
            "/api/v1/metering/usage",
            data=json.dumps({"customer_id": str(c.id), "request_id": "r1",
                             "idempotency_key": "k1", "billed_cost_micros": 60_000_000,
                             "tags": {"task": "t1"}}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw}")
        assert resp.status_code == 429
        body = resp.json()
        assert body["reason"] == "task_limit_exceeded"
        assert body["hard_stop"] is True
