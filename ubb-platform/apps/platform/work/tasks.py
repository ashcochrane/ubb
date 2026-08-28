import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.db.utils import OperationalError, InterfaceError
from django.utils import timezone

from core.vocabulary import TASK_STATUS_ACTIVE

logger = logging.getLogger(__name__)


@shared_task(
    queue="ubb_billing",
    autoretry_for=(OperationalError, InterfaceError),
    max_retries=3,
    retry_backoff=True,
)
def close_abandoned_tasks():
    """EXPIRE anything still active after longer than 1 hour.

    Safety net for work that was never explicitly closed by the SDK (client
    crash, network failure, forgotten close call) — and `expired` is what that
    is: nobody ever told UBB how it ended.

    ⚠ IT USED TO WRITE `completed` AND STAMP A MARKER IN METADATA (#408), so
    the state meant *the tenant declared delivery* OR *we gave up waiting* and
    no report could tell the two apart without reading a metadata key. The
    state says it now, so the marker is gone with it. Nothing else here moves:
    the windows, the cede to the reaper below, and the count returned are
    unchanged — the two windows become configurable and per kind of work in
    their own ticket.
    """
    from django.db.models import Q
    from apps.platform.work.models import Task

    now = timezone.now()
    cutoff = now - timedelta(hours=1)
    heartbeat_cutoff = now - timedelta(minutes=15)
    hard_age_cutoff = now - timedelta(hours=6)
    # Tier-2 (D10): a task that emitted an event recently is still ALIVE — do
    # not expire it just for being >1h old. BUT keep an absolute 6h ceiling
    # so no tenant (incl. off, which has no reaper) ever gets an
    # immortal task. And CEDE an enforcing tenant's EMITTED tasks to
    # reap_stale_tasks, which announces the stop to the tenant's workers;
    # never-emitted (last_event_at IS NULL) tasks stay eligible (the
    # original safety net, and for enforcing tenants this frees the
    # concurrency slot before 6h).
    #
    # ⚠ THE CEDE IS NOW ABOUT THE ANNOUNCEMENT, NOT THE STATE. Both sweepers
    # write `expired`, so which one wins the race no longer decides what the
    # row says — it decides only whether the tenant's idle workers are told.
    # That is a narrower reason for the cede than the one it replaces, and it
    # is the real one: the deterministic-terminal-state argument was solving a
    # problem the six states delete.
    stale_tasks = (
        Task.objects.filter(status=TASK_STATUS_ACTIVE, created_at__lt=cutoff)
        .exclude(Q(last_event_at__gte=heartbeat_cutoff) & Q(created_at__gte=hard_age_cutoff))
        .exclude(tenant__enforcement_mode="enforcing", last_event_at__isnull=False)
    )
    expired_count = 0

    from apps.platform.work.services import TaskService

    for task in stale_tasks.iterator():
        with transaction.atomic():
            # expire_task owns the terminal-state recheck and the downward
            # cascade (#38): an abandoned parent expires its still-active
            # contained work, which nobody reported on either.
            _, transitioned = TaskService.expire_task(task.id)
            if not transitioned:
                continue
            expired_count += 1

    if expired_count:
        logger.info("Expired %d abandoned tasks", expired_count)
    return expired_count


@shared_task(
    queue="ubb_billing",
    autoretry_for=(OperationalError, InterfaceError),
    max_retries=3,
    retry_backoff=True,
)
def reap_stale_tasks():
    """Tier-2 P5 (D10): EXPIRE stale active work for ENFORCING tenants.

    A unit that emitted events then went silent for >15 min (STALE), or any
    unit older than 6 h (STALE_MAX_AGE — a runaway hard ceiling), is expired
    and a task.limit_exceeded event (subtask.limit_exceeded for stale
    contained work, expired alone) is emitted so sibling/idle workers tear
    down. Reaping a parent cascades the expiry to its active contained work
    (#38) — note a parent whose contained work is still emitting is never
    heartbeat-stale, since rollup stamps the parent's heartbeat too.

    ⚠ IT USED TO WRITE `killed` (#408), which meant the same silence was
    recorded two ways — this sweeper's `killed` and the other's `completed` —
    and left `killed` unable to answer *how often do we blow ceilings* without
    filtering on a reason string first. Both of this module's sweepers converge
    on `expired`, and nothing else about the flow moves: the two windows, the
    enforcing-only rule and the announcement are all as they were.

    Enforcing-only: off tenants keep only the baseline close_abandoned_tasks
    (the silent >1h expiry, unannounced). Units that NEVER emitted are left to
    close_abandoned_tasks (no premature 15-min stop of a slow-to-start unit).
    The winning transition (inside expire_and_announce) guards against
    double-emit.
    """
    from django.db.models import Q
    from apps.platform.work.models import Task
    from apps.platform.work.reasons import STALE, STALE_MAX_AGE
    from apps.platform.work.services import TaskService
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
        candidates = (Task.objects.filter(tenant=tenant,
                                          status=TASK_STATUS_ACTIVE)
                      .filter(candidate_filter))
        for task in candidates.iterator():
            # created_at is immutable, so the reason is stable across the
            # unlocked candidate read; expire_and_announce owns the winning
            # transition, the downward cascade, the two-altitude event split,
            # and the exactly-once emit.
            reason = STALE_MAX_AGE if task.created_at < age_cutoff else STALE
            if TaskService.expire_and_announce(
                    task.id, reason,
                    tenant_id=tenant.id, customer_id=task.customer_id):
                reaped += 1

    if reaped:
        logger.info("Reaped %d stale tasks", reaped)
    return reaped
