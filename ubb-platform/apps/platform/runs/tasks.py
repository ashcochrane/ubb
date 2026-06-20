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
def close_abandoned_runs():
    """Close runs that have been active for longer than 1 hour.

    Safety net for runs that were never explicitly closed by the SDK
    (e.g., client crash, network failure, forgotten close call).
    """
    from django.db.models import Q
    from apps.platform.runs.models import Run

    now = timezone.now()
    cutoff = now - timedelta(hours=1)
    heartbeat_cutoff = now - timedelta(minutes=15)
    hard_age_cutoff = now - timedelta(hours=6)
    # Tier-2 (D10): a run that emitted an event recently is still ALIVE — do not
    # complete it just for being >1h old. BUT keep an absolute 6h ceiling so no
    # tenant (incl. off/advisory, which have no reaper) ever gets an immortal
    # run. And CEDE an enforcing tenant's EMITTED runs to reap_stale_runs so
    # their terminal state is deterministically 'killed' (+ run.limit_exceeded),
    # never silently 'completed' when this beat wins the race; never-emitted
    # (last_event_at IS NULL) runs stay eligible (the original safety net, and
    # for enforcing tenants this frees the concurrency slot before 6h).
    stale_runs = (
        Run.objects.filter(status="active", created_at__lt=cutoff)
        .exclude(Q(last_event_at__gte=heartbeat_cutoff) & Q(created_at__gte=hard_age_cutoff))
        .exclude(tenant__enforcement_mode="enforcing", last_event_at__isnull=False)
    )
    closed_count = 0

    for run in stale_runs.iterator():
        with transaction.atomic():
            locked = Run.objects.select_for_update().get(id=run.id)
            if locked.status != "active":
                continue
            locked.status = "completed"
            locked.completed_at = timezone.now()
            locked.metadata["auto_closed"] = True
            locked.save(update_fields=["status", "completed_at", "metadata", "updated_at"])
            closed_count += 1

    if closed_count:
        logger.info("Auto-closed %d abandoned runs", closed_count)
    return closed_count


@shared_task(
    queue="ubb_billing",
    autoretry_for=(OperationalError, InterfaceError),
    max_retries=3,
    retry_backoff=True,
)
def reap_stale_runs():
    """Tier-2 P5 (D10): KILL stale active runs for ENFORCING tenants.

    A run that emitted events then went silent for >15 min (STALE), or any run
    older than 6 h (STALE_MAX_AGE — a runaway hard ceiling), is killed and a
    run.limit_exceeded event is emitted so sibling/idle workers tear down.

    Enforcing-only: off/advisory tenants keep only the baseline
    close_abandoned_runs (graceful >1h complete). Runs that NEVER emitted are
    left to close_abandoned_runs (no premature 15-min kill of a slow-to-start
    run). The winning active->killed transition (select_for_update) guards
    against double-emit.
    """
    from django.db.models import Q
    from apps.platform.runs.models import Run
    from apps.platform.runs.reasons import STALE, STALE_MAX_AGE
    from apps.platform.tenants.models import Tenant
    from apps.platform.tenants.flags import enforcing
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import RunLimitExceeded

    now = timezone.now()
    age_cutoff = now - timedelta(hours=6)
    reaped = 0

    for tenant in Tenant.objects.filter(enforcement_mode="enforcing").iterator():
        if not enforcing(tenant):  # defensive: honor the single flag helper
            continue
        # Per-tenant stale window (Tenant.run_stale_seconds; 0 disables the
        # heartbeat reaper — the 6h max-age ceiling still applies).
        stale_seconds = tenant.run_stale_seconds or 0
        age_filter = Q(created_at__lt=age_cutoff)
        if stale_seconds > 0:
            heartbeat_cutoff = now - timedelta(seconds=stale_seconds)
            candidate_filter = age_filter | Q(
                last_event_at__isnull=False, last_event_at__lt=heartbeat_cutoff)
        else:
            candidate_filter = age_filter
        candidates = Run.objects.filter(tenant=tenant, status="active").filter(candidate_filter)
        for run in candidates.iterator():
            with transaction.atomic():
                locked = Run.objects.select_for_update().get(id=run.id)
                if locked.status != "active":
                    continue  # another worker / the endpoint already terminated it
                # Reason from the LOCKED snapshot (robust to a heartbeat that
                # arrived during the unlocked candidate read).
                reason = STALE_MAX_AGE if locked.created_at < age_cutoff else STALE
                locked.status = "killed"
                locked.completed_at = now
                locked.metadata = {**locked.metadata, "kill_reason": reason}
                locked.save(update_fields=["status", "completed_at", "metadata", "updated_at"])
                write_event(RunLimitExceeded(
                    tenant_id=str(tenant.id), customer_id=str(locked.customer_id),
                    billing_owner_id=str(locked.billing_owner_id or ""),
                    run_id=str(locked.id), external_run_id=locked.external_run_id,
                    task_id=locked.task_id, reason=reason, scope="run",
                    total_cost_micros=locked.total_cost_micros))
            reaped += 1

    if reaped:
        logger.info("Reaped %d stale runs", reaped)
    return reaped
