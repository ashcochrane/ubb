"""P5: per-owner concurrency cap (COUNT active runs) + stale-run reaper.

The concurrency cap is enforcing-only and counts ACTIVE runs for the billing
owner (pooled business shares one cap). The reaper KILLS stale active runs of
enforcing tenants (heartbeat >15min or age >6h) and emits run.limit_exceeded;
close_abandoned_runs stays the baseline >1h completer but skips alive (recent
heartbeat) runs.
"""
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.billing.gating.models import RiskConfig
from apps.billing.gating.services.risk_service import RiskService
from apps.platform.events.models import OutboxEvent
from apps.platform.runs.models import Run
from apps.platform.runs.services import RunService
from apps.platform.runs.tasks import close_abandoned_runs, reap_stale_runs
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant


def _tenant(mode="prepaid", enf="enforcing", stale=900):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf,
                                 run_stale_seconds=stale)


def _run(t, c, owner_id):
    return RunService.create_run(tenant=t, customer=c, balance_snapshot_micros=0,
                                 billing_owner_id=owner_id)


@pytest.mark.django_db
class TestConcurrencyCap:
    def setup_method(self):
        cache.clear()

    def test_blocks_new_run_at_limit(self):
        t = _tenant()
        RiskConfig.objects.create(tenant=t, max_concurrent_requests=2)
        c = Customer.objects.create(tenant=t, external_id="c1")
        _run(t, c, c.id)
        _run(t, c, c.id)
        res = RiskService.check(c, create_run=True)
        assert res["allowed"] is False
        assert res["reason"] == "concurrency_limit"
        assert res["run_id"] is None

    def test_off_tenant_not_capped(self):
        t = _tenant(enf="off")
        RiskConfig.objects.create(tenant=t, max_concurrent_requests=2)
        c = Customer.objects.create(tenant=t, external_id="c1")
        for _ in range(3):
            _run(t, c, c.id)
        res = RiskService.check(c, create_run=True)
        assert res["allowed"] is True

    def test_pooled_business_shares_cap_counted_per_owner(self):
        t = _tenant()
        RiskConfig.objects.create(tenant=t, max_concurrent_requests=2)
        biz = Customer.objects.create(tenant=t, external_id="biz",
                                      account_type="business", billing_topology="pooled")
        s1 = Customer.objects.create(tenant=t, external_id="s1", account_type="seat", parent=biz)
        s2 = Customer.objects.create(tenant=t, external_id="s2", account_type="seat", parent=biz)
        _run(t, s1, biz.id)  # both runs pin the business as billing owner
        _run(t, s2, biz.id)
        res = RiskService.check(s1, create_run=True)  # 3rd run, any seat -> blocked
        assert res["allowed"] is False and res["reason"] == "concurrency_limit"


@pytest.mark.django_db
class TestReaper:
    def setup_method(self):
        cache.clear()

    def _emitted(self, run_id):
        return OutboxEvent.objects.filter(
            event_type="run.limit_exceeded", payload__run_id=str(run_id)).exists()

    def test_kills_stale_heartbeat_run_and_emits(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        run = _run(t, c, c.id)
        Run.objects.filter(id=run.id).update(last_event_at=timezone.now() - timedelta(minutes=20))
        assert reap_stale_runs() == 1
        run.refresh_from_db()
        assert run.status == "killed" and run.metadata.get("kill_reason") == "stale"
        assert self._emitted(run.id)

    def test_kills_max_age_run_even_with_recent_heartbeat(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        run = _run(t, c, c.id)
        Run.objects.filter(id=run.id).update(
            created_at=timezone.now() - timedelta(hours=7),
            last_event_at=timezone.now() - timedelta(minutes=1))
        reap_stale_runs()
        run.refresh_from_db()
        assert run.status == "killed" and run.metadata.get("kill_reason") == "stale_max_age"

    def test_skips_never_emitted_run_before_max_age(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        run = _run(t, c, c.id)  # last_event_at is None
        Run.objects.filter(id=run.id).update(created_at=timezone.now() - timedelta(minutes=30))
        reap_stale_runs()
        run.refresh_from_db()
        assert run.status == "active"  # never-emitted run is NOT 15-min reaped

    def test_no_op_for_off_tenant(self):
        t = _tenant(enf="off")
        c = Customer.objects.create(tenant=t, external_id="c1")
        run = _run(t, c, c.id)
        Run.objects.filter(id=run.id).update(last_event_at=timezone.now() - timedelta(minutes=20))
        reap_stale_runs()
        run.refresh_from_db()
        assert run.status == "active"


@pytest.mark.django_db
class TestCloseAbandonedHeartbeatSkip:
    def setup_method(self):
        cache.clear()

    def test_skips_alive_run_completes_silent_run(self):
        t = _tenant(enf="off")
        c = Customer.objects.create(tenant=t, external_id="c1")
        alive = _run(t, c, c.id)
        Run.objects.filter(id=alive.id).update(
            created_at=timezone.now() - timedelta(hours=2),
            last_event_at=timezone.now() - timedelta(minutes=1))
        silent = _run(t, c, c.id)
        Run.objects.filter(id=silent.id).update(created_at=timezone.now() - timedelta(hours=2))
        close_abandoned_runs()
        alive.refresh_from_db()
        silent.refresh_from_db()
        assert alive.status == "active"      # recent heartbeat -> skipped
        assert silent.status == "completed"  # no recent activity -> safety-net closed

    def test_completes_alive_run_past_absolute_6h_ceiling(self):
        # Even a still-emitting run is completed once past the 6h ceiling, so no
        # off/advisory tenant (no reaper) gets an immortal run.
        t = _tenant(enf="off")
        c = Customer.objects.create(tenant=t, external_id="c1")
        run = _run(t, c, c.id)
        Run.objects.filter(id=run.id).update(
            created_at=timezone.now() - timedelta(hours=7),
            last_event_at=timezone.now() - timedelta(minutes=1))
        close_abandoned_runs()
        run.refresh_from_db()
        assert run.status == "completed"

    def test_cedes_enforcing_emitted_stale_run_to_reaper(self):
        # An enforcing tenant's emitted+stale+>1h run must NOT be 'completed' by
        # close_abandoned (deterministic terminal state -> the reaper kills it).
        t = _tenant(enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1")
        run = _run(t, c, c.id)
        Run.objects.filter(id=run.id).update(
            created_at=timezone.now() - timedelta(minutes=90),
            last_event_at=timezone.now() - timedelta(minutes=20))
        close_abandoned_runs()
        run.refresh_from_db()
        assert run.status == "active"  # ceded to the reaper, not completed


@pytest.mark.django_db
class TestP5ReviewFixes:
    def setup_method(self):
        cache.clear()

    def test_concurrency_cap_zero_disables(self):
        t = _tenant()
        RiskConfig.objects.create(tenant=t, max_concurrent_requests=0)
        c = Customer.objects.create(tenant=t, external_id="c1")
        for _ in range(3):
            _run(t, c, c.id)
        assert RiskService.check(c, create_run=True)["allowed"] is True

    def test_concurrency_cap_negative_does_not_brick(self):
        t = _tenant()
        RiskConfig.objects.create(tenant=t, max_concurrent_requests=-1)
        c = Customer.objects.create(tenant=t, external_id="c1")
        # 0 active runs; a negative cap must NOT block (no -1 >= active=0 trap)
        assert RiskService.check(c, create_run=True)["allowed"] is True

    def test_reaper_respects_tenant_run_stale_seconds(self):
        t = _tenant(stale=1800)  # 30-min window
        c = Customer.objects.create(tenant=t, external_id="c1")
        run = _run(t, c, c.id)
        Run.objects.filter(id=run.id).update(last_event_at=timezone.now() - timedelta(minutes=20))
        reap_stale_runs()
        run.refresh_from_db()
        assert run.status == "active"  # 20min < 30min window -> not stale yet
        Run.objects.filter(id=run.id).update(last_event_at=timezone.now() - timedelta(minutes=40))
        reap_stale_runs()
        run.refresh_from_db()
        assert run.status == "killed"

    def test_reaper_zero_stale_disables_heartbeat_keeps_max_age(self):
        t = _tenant(stale=0)
        c = Customer.objects.create(tenant=t, external_id="c1")
        run = _run(t, c, c.id)
        Run.objects.filter(id=run.id).update(last_event_at=timezone.now() - timedelta(hours=1))
        reap_stale_runs()
        run.refresh_from_db()
        assert run.status == "active"  # heartbeat reaper disabled (stale=0)
        Run.objects.filter(id=run.id).update(created_at=timezone.now() - timedelta(hours=7))
        reap_stale_runs()
        run.refresh_from_db()
        assert run.status == "killed"  # 6h max-age still applies
