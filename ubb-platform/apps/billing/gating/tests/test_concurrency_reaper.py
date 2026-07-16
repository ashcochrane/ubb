"""P5: per-owner concurrency cap (COUNT active tasks) + stale-task reaper.

The concurrency cap is enforcing-only and counts ACTIVE tasks for the billing
owner (pooled business shares one cap). The reaper KILLS stale active tasks of
enforcing tenants (heartbeat past the tenant window or age >6h) and emits
task.limit_exceeded; close_abandoned_tasks stays the baseline >1h completer
but skips alive (recent heartbeat) tasks.
"""
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.billing.gating.models import RiskConfig
from apps.billing.gating.services.risk_service import RiskService
from apps.platform.events.models import OutboxEvent
from apps.platform.tasks.models import Task
from apps.platform.tasks.services import TaskService
from apps.platform.tasks.tasks import close_abandoned_tasks, reap_stale_tasks
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant


def _tenant(mode="prepaid", enf="enforcing", stale=900):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf,
                                 task_stale_seconds=stale)


def _task(t, c, owner_id):
    return TaskService.create_task(tenant=t, customer=c, balance_snapshot_micros=0,
                                   billing_owner_id=owner_id)


@pytest.mark.django_db
class TestConcurrencyCap:
    def setup_method(self):
        cache.clear()

    def test_blocks_new_task_at_limit(self):
        t = _tenant()
        RiskConfig.objects.create(tenant=t, max_concurrent_requests=2)
        c = Customer.objects.create(tenant=t, external_id="c1")
        _task(t, c, c.id)
        _task(t, c, c.id)
        res = RiskService.check(c, create_task=True)
        assert res["allowed"] is False
        assert res["reason"] == "concurrency_limit"
        assert res["task_id"] is None

    def test_off_tenant_not_capped(self):
        t = _tenant(enf="off")
        RiskConfig.objects.create(tenant=t, max_concurrent_requests=2)
        c = Customer.objects.create(tenant=t, external_id="c1")
        for _ in range(3):
            _task(t, c, c.id)
        res = RiskService.check(c, create_task=True)
        assert res["allowed"] is True

    def test_pooled_business_shares_cap_counted_per_owner(self):
        t = _tenant()
        RiskConfig.objects.create(tenant=t, max_concurrent_requests=2)
        biz = Customer.objects.create(tenant=t, external_id="biz",
                                      account_type="business", billing_topology="pooled")
        s1 = Customer.objects.create(tenant=t, external_id="s1", account_type="seat", parent=biz)
        s2 = Customer.objects.create(tenant=t, external_id="s2", account_type="seat", parent=biz)
        _task(t, s1, biz.id)  # both tasks pin the business as billing owner
        _task(t, s2, biz.id)
        res = RiskService.check(s1, create_task=True)  # 3rd task, any seat -> blocked
        assert res["allowed"] is False and res["reason"] == "concurrency_limit"


@pytest.mark.django_db
class TestReaper:
    def setup_method(self):
        cache.clear()

    def _emitted(self, task_id):
        return OutboxEvent.objects.filter(
            event_type="task.limit_exceeded", payload__task_id=str(task_id)).exists()

    def test_kills_stale_heartbeat_task_and_emits(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        task = _task(t, c, c.id)
        Task.objects.filter(id=task.id).update(last_event_at=timezone.now() - timedelta(minutes=20))
        assert reap_stale_tasks() == 1
        task.refresh_from_db()
        assert task.status == "killed" and task.metadata.get("kill_reason") == "stale"
        assert self._emitted(task.id)
        payload = OutboxEvent.objects.get(
            event_type="task.limit_exceeded", payload__task_id=str(task.id)).payload
        assert payload["reason"] == "stale"
        assert payload["total_billed_cost_micros"] == 0
        assert payload["total_provider_cost_micros"] == 0
        assert "scope" not in payload
        assert "limit_micros" not in payload

    def test_kills_max_age_task_even_with_recent_heartbeat(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        task = _task(t, c, c.id)
        Task.objects.filter(id=task.id).update(
            created_at=timezone.now() - timedelta(hours=7),
            last_event_at=timezone.now() - timedelta(minutes=1))
        reap_stale_tasks()
        task.refresh_from_db()
        assert task.status == "killed" and task.metadata.get("kill_reason") == "stale_max_age"

    def test_skips_never_emitted_task_before_max_age(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        task = _task(t, c, c.id)  # last_event_at is None
        Task.objects.filter(id=task.id).update(created_at=timezone.now() - timedelta(minutes=30))
        reap_stale_tasks()
        task.refresh_from_db()
        assert task.status == "active"  # never-emitted task is NOT 15-min reaped

    def test_no_op_for_off_tenant(self):
        t = _tenant(enf="off")
        c = Customer.objects.create(tenant=t, external_id="c1")
        task = _task(t, c, c.id)
        Task.objects.filter(id=task.id).update(last_event_at=timezone.now() - timedelta(minutes=20))
        reap_stale_tasks()
        task.refresh_from_db()
        assert task.status == "active"


@pytest.mark.django_db
class TestCloseAbandonedHeartbeatSkip:
    def setup_method(self):
        cache.clear()

    def test_skips_alive_task_completes_silent_task(self):
        t = _tenant(enf="off")
        c = Customer.objects.create(tenant=t, external_id="c1")
        alive = _task(t, c, c.id)
        Task.objects.filter(id=alive.id).update(
            created_at=timezone.now() - timedelta(hours=2),
            last_event_at=timezone.now() - timedelta(minutes=1))
        silent = _task(t, c, c.id)
        Task.objects.filter(id=silent.id).update(created_at=timezone.now() - timedelta(hours=2))
        close_abandoned_tasks()
        alive.refresh_from_db()
        silent.refresh_from_db()
        assert alive.status == "active"      # recent heartbeat -> skipped
        assert silent.status == "completed"  # no recent activity -> safety-net closed

    def test_completes_alive_task_past_absolute_6h_ceiling(self):
        # Even a still-emitting task is completed once past the 6h ceiling, so no
        # off/advisory tenant (no reaper) gets an immortal task.
        t = _tenant(enf="off")
        c = Customer.objects.create(tenant=t, external_id="c1")
        task = _task(t, c, c.id)
        Task.objects.filter(id=task.id).update(
            created_at=timezone.now() - timedelta(hours=7),
            last_event_at=timezone.now() - timedelta(minutes=1))
        close_abandoned_tasks()
        task.refresh_from_db()
        assert task.status == "completed"

    def test_cedes_enforcing_emitted_stale_task_to_reaper(self):
        # An enforcing tenant's emitted+stale+>1h task must NOT be 'completed' by
        # close_abandoned (deterministic terminal state -> the reaper kills it).
        t = _tenant(enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1")
        task = _task(t, c, c.id)
        Task.objects.filter(id=task.id).update(
            created_at=timezone.now() - timedelta(minutes=90),
            last_event_at=timezone.now() - timedelta(minutes=20))
        close_abandoned_tasks()
        task.refresh_from_db()
        assert task.status == "active"  # ceded to the reaper, not completed


@pytest.mark.django_db
class TestP5ReviewFixes:
    def setup_method(self):
        cache.clear()

    def test_concurrency_cap_zero_disables(self):
        t = _tenant()
        RiskConfig.objects.create(tenant=t, max_concurrent_requests=0)
        c = Customer.objects.create(tenant=t, external_id="c1")
        for _ in range(3):
            _task(t, c, c.id)
        assert RiskService.check(c, create_task=True)["allowed"] is True

    def test_concurrency_cap_negative_does_not_brick(self):
        t = _tenant()
        RiskConfig.objects.create(tenant=t, max_concurrent_requests=-1)
        c = Customer.objects.create(tenant=t, external_id="c1")
        # 0 active tasks; a negative cap must NOT block (no -1 >= active=0 trap)
        assert RiskService.check(c, create_task=True)["allowed"] is True

    def test_reaper_respects_tenant_task_stale_seconds(self):
        t = _tenant(stale=1800)  # 30-min window
        c = Customer.objects.create(tenant=t, external_id="c1")
        task = _task(t, c, c.id)
        Task.objects.filter(id=task.id).update(last_event_at=timezone.now() - timedelta(minutes=20))
        reap_stale_tasks()
        task.refresh_from_db()
        assert task.status == "active"  # 20min < 30min window -> not stale yet
        Task.objects.filter(id=task.id).update(last_event_at=timezone.now() - timedelta(minutes=40))
        reap_stale_tasks()
        task.refresh_from_db()
        assert task.status == "killed"

    def test_reaper_zero_stale_disables_heartbeat_keeps_max_age(self):
        t = _tenant(stale=0)
        c = Customer.objects.create(tenant=t, external_id="c1")
        task = _task(t, c, c.id)
        Task.objects.filter(id=task.id).update(last_event_at=timezone.now() - timedelta(hours=1))
        reap_stale_tasks()
        task.refresh_from_db()
        assert task.status == "active"  # heartbeat reaper disabled (stale=0)
        Task.objects.filter(id=task.id).update(created_at=timezone.now() - timedelta(hours=7))
        reap_stale_tasks()
        task.refresh_from_db()
        assert task.status == "killed"  # 6h max-age still applies
