"""The two sweepers: the announcing stale-work reaper and the abandoned-close.

The reaper EXPIRES stale active work of enforcing tenants (past its silence
window or past its absolute deadline) and announces `task.expired`;
close_abandoned_tasks stays the baseline >1h sweeper but skips alive (recent
heartbeat) tasks. Both give crashed work a deterministic terminal state,
which is what they have always been for.

This module was `test_concurrency_reaper.py` and also held five cases for a
per-owner cap on work already running; #455 deleted that control outright
(#150 §12.5) and the cases with it, and the module is renamed for what it
still proves. Nothing below was changed by that deletion.

⚠ BOTH SWEEPERS WRITE `expired` (#408) — nobody ever told UBB how the work
ended, which is the one thing a silence CAN say. `killed` is reserved for a
spend signal, so the assertions below name the state each sweeper is entitled
to write and never the other. Since the terminal-event split the ANNOUNCEMENT
says the same thing (#140 §4.3): this reaper can only ever emit the expiry, and
the cases below name the class rather than a string so that stays checked.

⚠ EVERY WINDOW HERE IS NOW A RESOLVED ONE (#412). The tenants below declare no
kind of work, so each falls to the rung it always ran on — the tenant's own
default where these fixtures set one, and UBB's backstop (the same fifteen
minutes and six hours these cases were written against) where they do not. The
cases stand unchanged for that reason; what a DECLARED kind of work does to
either window is the subject of
`apps/platform/work/tests/test_the_windows_belong_to_the_kind_of_work.py`.
"""
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import TaskExpired
from apps.platform.work import reasons
from apps.platform.work.models import Task
from apps.platform.work.services import TaskService
from apps.platform.work.tasks import close_abandoned_tasks, reap_stale_tasks
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    TASK_STATUS_ACTIVE, TASK_STATUS_EXPIRED, TASK_STATUS_KILLED)


def _tenant(mode="prepaid", enf="enforcing", stale=900):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf,
                                 task_stale_seconds=stale)


def _task(t, c, owner_id):
    return TaskService.create_task(tenant=t, customer=c, balance_snapshot_micros=0,
                                   billing_owner_id=owner_id)


@pytest.mark.django_db
class TestReaper:
    def setup_method(self):
        cache.clear()

    def _emitted(self, task_id):
        return OutboxEvent.objects.filter(
            event_type=TaskExpired.EVENT_TYPE,
            payload__task_id=str(task_id)).exists()

    def test_expires_stale_heartbeat_task_and_emits(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        task = _task(t, c, c.id)
        Task.objects.filter(id=task.id).update(last_event_at=timezone.now() - timedelta(minutes=20))
        assert reap_stale_tasks() == 1
        task.refresh_from_db()
        assert task.status == TASK_STATUS_EXPIRED
        assert task.metadata.get("kill_reason") == reasons.SILENCE_WINDOW
        assert self._emitted(task.id)
        payload = OutboxEvent.objects.get(
            event_type=TaskExpired.EVENT_TYPE,
            payload__task_id=str(task.id)).payload
        assert payload["reason_code"] == reasons.SILENCE_WINDOW
        assert payload["total_billed_cost_micros"] == 0
        assert payload["total_provider_cost_micros"] == 0
        assert "scope" not in payload
        assert "limit_micros" not in payload

    def test_expires_max_age_task_even_with_recent_heartbeat(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        task = _task(t, c, c.id)
        Task.objects.filter(id=task.id).update(
            created_at=timezone.now() - timedelta(hours=7),
            last_event_at=timezone.now() - timedelta(minutes=1))
        reap_stale_tasks()
        task.refresh_from_db()
        assert task.status == TASK_STATUS_EXPIRED
        assert task.metadata.get("kill_reason") == reasons.STALE_MAX_AGE

    def test_skips_never_emitted_task_before_max_age(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        task = _task(t, c, c.id)  # last_event_at is None
        Task.objects.filter(id=task.id).update(created_at=timezone.now() - timedelta(minutes=30))
        reap_stale_tasks()
        task.refresh_from_db()
        assert task.status == TASK_STATUS_ACTIVE  # never-emitted task is NOT 15-min reaped

    def test_no_op_for_off_tenant(self):
        t = _tenant(enf="off")
        c = Customer.objects.create(tenant=t, external_id="c1")
        task = _task(t, c, c.id)
        Task.objects.filter(id=task.id).update(last_event_at=timezone.now() - timedelta(minutes=20))
        reap_stale_tasks()
        task.refresh_from_db()
        assert task.status == TASK_STATUS_ACTIVE


@pytest.mark.django_db
class TestCloseAbandonedHeartbeatSkip:
    def setup_method(self):
        cache.clear()

    def test_skips_alive_task_expires_silent_task(self):
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
        assert alive.status == TASK_STATUS_ACTIVE   # recent heartbeat -> skipped
        assert silent.status == TASK_STATUS_EXPIRED  # no recent activity -> swept

    def test_expires_alive_task_past_absolute_6h_ceiling(self):
        # Even a still-emitting task is expired once past the 6h ceiling, so no
        # off tenant (no reaper) gets an immortal task.
        t = _tenant(enf="off")
        c = Customer.objects.create(tenant=t, external_id="c1")
        task = _task(t, c, c.id)
        Task.objects.filter(id=task.id).update(
            created_at=timezone.now() - timedelta(hours=7),
            last_event_at=timezone.now() - timedelta(minutes=1))
        close_abandoned_tasks()
        task.refresh_from_db()
        assert task.status == TASK_STATUS_EXPIRED

    def test_cedes_enforcing_emitted_stale_task_to_reaper(self):
        # An enforcing tenant's emitted+stale+>1h task is left to the reaper.
        # Both sweepers write the same state now (#408), so the cede buys the
        # ANNOUNCEMENT rather than a deterministic terminal state: the reaper
        # tells the tenant's idle workers, and this beat does not.
        t = _tenant(enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1")
        task = _task(t, c, c.id)
        Task.objects.filter(id=task.id).update(
            created_at=timezone.now() - timedelta(minutes=90),
            last_event_at=timezone.now() - timedelta(minutes=20))
        close_abandoned_tasks()
        task.refresh_from_db()
        assert task.status == TASK_STATUS_ACTIVE  # ceded to the reaper, not completed


@pytest.mark.django_db
class TestP5ReviewFixes:
    def setup_method(self):
        cache.clear()

    def test_reaper_respects_tenant_task_stale_seconds(self):
        t = _tenant(stale=1800)  # 30-min window
        c = Customer.objects.create(tenant=t, external_id="c1")
        task = _task(t, c, c.id)
        Task.objects.filter(id=task.id).update(last_event_at=timezone.now() - timedelta(minutes=20))
        reap_stale_tasks()
        task.refresh_from_db()
        assert task.status == TASK_STATUS_ACTIVE  # 20min < 30min window -> not stale yet
        Task.objects.filter(id=task.id).update(last_event_at=timezone.now() - timedelta(minutes=40))
        reap_stale_tasks()
        task.refresh_from_db()
        assert task.status == TASK_STATUS_EXPIRED

    def test_reaper_zero_stale_disables_heartbeat_keeps_max_age(self):
        t = _tenant(stale=0)
        c = Customer.objects.create(tenant=t, external_id="c1")
        task = _task(t, c, c.id)
        Task.objects.filter(id=task.id).update(last_event_at=timezone.now() - timedelta(hours=1))
        reap_stale_tasks()
        task.refresh_from_db()
        assert task.status == TASK_STATUS_ACTIVE  # heartbeat reaper disabled (stale=0)
        Task.objects.filter(id=task.id).update(created_at=timezone.now() - timedelta(hours=7))
        reap_stale_tasks()
        task.refresh_from_db()
        assert task.status == TASK_STATUS_EXPIRED  # 6h max-age still applies
