import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.db.utils import OperationalError, InterfaceError
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    queue="ubb_billing",
    autoretry_for=(OperationalError, InterfaceError),
    max_retries=3,
    retry_backoff=True,
)
def close_abandoned_tasks():
    """Close tasks that have been active for longer than 1 hour.

    Safety net for tasks that were never explicitly closed by the SDK
    (e.g., client crash, network failure, forgotten close call).
    """
    from django.db.models import Q
    from apps.platform.tasks.models import Task

    now = timezone.now()
    cutoff = now - timedelta(hours=1)
    heartbeat_cutoff = now - timedelta(minutes=15)
    hard_age_cutoff = now - timedelta(hours=6)
    # Tier-2 (D10): a task that emitted an event recently is still ALIVE — do
    # not complete it just for being >1h old. BUT keep an absolute 6h ceiling
    # so no tenant (incl. off, which has no reaper) ever gets an
    # immortal task. And CEDE an enforcing tenant's EMITTED tasks to
    # reap_stale_tasks so their terminal state is deterministically 'killed'
    # (+ task.limit_exceeded), never silently 'completed' when this beat wins
    # the race; never-emitted (last_event_at IS NULL) tasks stay eligible (the
    # original safety net, and for enforcing tenants this frees the
    # concurrency slot before 6h).
    stale_tasks = (
        Task.objects.filter(status="active", created_at__lt=cutoff)
        .exclude(Q(last_event_at__gte=heartbeat_cutoff) & Q(created_at__gte=hard_age_cutoff))
        .exclude(tenant__enforcement_mode="enforcing", last_event_at__isnull=False)
    )
    closed_count = 0

    from apps.platform.tasks.services import TaskService

    for task in stale_tasks.iterator():
        with transaction.atomic():
            # complete_task owns the terminal-state recheck and the downward
            # cascade (#38): auto-closing an abandoned parent auto-completes
            # its active subtasks, same as an explicit close.
            completed, transitioned = TaskService.complete_task(task.id)
            if not transitioned:
                continue
            completed.metadata["auto_closed"] = True
            completed.save(update_fields=["metadata", "updated_at"])
            closed_count += 1

    if closed_count:
        logger.info("Auto-closed %d abandoned tasks", closed_count)
    return closed_count


@shared_task(
    queue="ubb_billing",
    autoretry_for=(OperationalError, InterfaceError),
    max_retries=3,
    retry_backoff=True,
)
def reap_stale_tasks():
    """Tier-2 P5 (D10): KILL stale active tasks for ENFORCING tenants.

    A task that emitted events then went silent for >15 min (STALE), or any
    task older than 6 h (STALE_MAX_AGE — a runaway hard ceiling), is killed
    and a task.limit_exceeded event (subtask.limit_exceeded for a stale
    subtask, killed alone) is emitted so sibling/idle workers tear down.
    Reaping a parent cascades the kill to its active subtasks (#38) — note a
    parent whose subtasks are still emitting is never heartbeat-stale, since
    rollup stamps the parent's heartbeat too.

    Enforcing-only: off tenants keep only the baseline
    close_abandoned_tasks (graceful >1h complete). Tasks that NEVER emitted
    are left to close_abandoned_tasks (no premature 15-min kill of a
    slow-to-start task). The winning active->killed transition (inside
    kill_and_announce) guards against double-emit.
    """
    from django.db.models import Q
    from apps.platform.tasks.models import Task
    from apps.platform.tasks.reasons import STALE, STALE_MAX_AGE
    from apps.platform.tasks.services import TaskService
    from apps.platform.tenants.models import Tenant
    from apps.platform.tenants.flags import enforcing

    now = timezone.now()
    age_cutoff = now - timedelta(hours=6)
    reaped = 0

    for tenant in Tenant.objects.filter(enforcement_mode="enforcing").iterator():
        if not enforcing(tenant):  # defensive: honor the single flag helper
            continue
        # Per-tenant stale window (Tenant.task_stale_seconds; 0 disables the
        # heartbeat reaper — the 6h max-age ceiling still applies).
        stale_seconds = tenant.task_stale_seconds or 0
        age_filter = Q(created_at__lt=age_cutoff)
        if stale_seconds > 0:
            heartbeat_cutoff = now - timedelta(seconds=stale_seconds)
            candidate_filter = age_filter | Q(
                last_event_at__isnull=False, last_event_at__lt=heartbeat_cutoff)
        else:
            candidate_filter = age_filter
        candidates = Task.objects.filter(tenant=tenant, status="active").filter(candidate_filter)
        for task in candidates.iterator():
            # created_at is immutable, so the reason is stable across the
            # unlocked candidate read; kill_and_announce owns the winning
            # active->killed transition, the downward cascade, the
            # task/subtask event split, and the exactly-once emit.
            reason = STALE_MAX_AGE if task.created_at < age_cutoff else STALE
            if TaskService.kill_and_announce(
                    task.id, reason,
                    tenant_id=tenant.id, customer_id=task.customer_id):
                reaped += 1

    if reaped:
        logger.info("Reaped %d stale tasks", reaped)
    return reaped
