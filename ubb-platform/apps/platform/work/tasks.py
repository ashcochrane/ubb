import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.db.utils import OperationalError, InterfaceError
from django.utils import timezone

from core.vocabulary import (
    TASK_STATUS_ACTIVE, TASK_TYPE_KIND_SUBTASK, TASK_TYPE_KIND_TASK,
    TRIGGER_SOURCE_STALE_REAPER)

logger = logging.getLogger(__name__)


def _declaration_of(task):
    """The key this unit's expiry policy is resolved under — its altitude and
    the kind of work it declared.

    The altitude comes from the parent link and from nothing else, because one
    column carries the declared kind at either altitude and the link is the
    only thing that says which one a row is at (#407).
    """
    kind = TASK_TYPE_KIND_SUBTASK if task.parent_id else TASK_TYPE_KIND_TASK
    return (kind, task.task_type)


def _declaring(declaration):
    """Every unit under one declared kind of work, at its own altitude."""
    kind, key = declaration
    return Q(task_type=key, parent__isnull=(kind == TASK_TYPE_KIND_TASK))


def _deadline_instant(absolute_seconds, now):
    """When a unit registered at this instant runs out of time.

    One expression, because the same arithmetic is asked twice for two
    different jobs and they must not drift: once as a bound the database
    filters on, and once per candidate row to say WHICH window ran out. A
    second spelling of it would put a sweeper's filter and its reason one
    rounding apart, and the row it disagreed about is exactly the one on the
    boundary.
    """
    return now - timedelta(seconds=absolute_seconds)


def _past_a_window(windows, now):
    """Everything whose OWN silence window or absolute deadline has elapsed.

    One expression rather than a query per kind of work: each declared kind
    contributes its own pair of cutoffs, and everything the tenant has not
    declared contributes the fallback pair under the negation of all of them.
    A sweeper that ran one query per declared kind would ask the same table the
    same question N times and still have to re-resolve each row's pair to name
    a reason, so the loop that builds this is the cheaper half either way.

    Silence is measured from the last report and skips a unit that has never
    made one — that is not silence, it is a unit that has not started talking,
    and its callers are the baseline sweeper's business. The absolute deadline
    is measured from creation and applies to every unit whatever it has done.
    """
    from apps.platform.work.queries import EXPIRY_LADDER_FALLBACK

    declared = Q()
    expression = Q()
    for declaration, pair in windows.items():
        if declaration is EXPIRY_LADDER_FALLBACK:
            continue
        declared |= _declaring(declaration)
        expression |= _declaring(declaration) & _elapsed(pair, now)

    fallback = _elapsed(windows[EXPIRY_LADDER_FALLBACK], now)
    # `~Q()` is not "nothing"; an empty Q negates to a refusal Django cannot
    # render usefully, so a tenant that has declared no kind of work gets the
    # fallback over the whole table rather than over "everything except the
    # empty set".
    return expression | (fallback if not declared.children
                         else ~declared & fallback)


def _elapsed(pair, now):
    """One pair of windows, as a condition on a unit's two timestamps."""
    elapsed = Q(created_at__lt=_deadline_instant(pair.absolute, now))
    if pair.silence is not None:
        elapsed |= Q(last_event_at__isnull=False,
                     last_event_at__lt=now - timedelta(seconds=pair.silence))
    return elapsed


def _reason_for(task, windows, now):
    """Which of the two windows this unit ran out of, named by constant.

    The absolute deadline is asked FIRST and answers whenever it has elapsed,
    which keeps the more serious of the two facts on the record: a unit past
    its deadline is past it whether or not it also went quiet, and reporting
    the silence instead would say the tenant stopped talking about work that
    had in fact run out of time.
    """
    from apps.platform.work.queries import EXPIRY_LADDER_FALLBACK
    from apps.platform.work.reasons import SILENCE_WINDOW, STALE_MAX_AGE

    pair = windows.get(_declaration_of(task),
                       windows[EXPIRY_LADDER_FALLBACK])
    past_deadline = task.created_at < _deadline_instant(pair.absolute, now)
    return STALE_MAX_AGE if past_deadline else SILENCE_WINDOW


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
    state says it now, so the marker is gone with it.

    ⚠ THE TWO WINDOWS IT USED TO SPELL AS DURATIONS ARE NOW A LADDER (#412),
    and this sweeper reads exactly the same one the announcing sweeper below
    reads — a kind of work's own declaration, then the tenant's default, then
    UBB's backstop. The backstops are the numbers that were spelled here, so a
    tenant that has declared nothing is swept exactly as it was.

    ⚠ WHAT THE WINDOWS DECIDE HERE IS LIVENESS, NOT REAPING, and that is the
    pre-existing division of labour rather than a limit of the ladder. The
    one-hour floor is this sweeper's whole subject: work nobody closed. A unit
    that reported inside its silence window and is still inside its absolute
    deadline is ALIVE and exempt from that floor; a unit past either is not
    exempt from it, and is swept once it is also older than an hour. Reaping
    the moment a window elapses is the ANNOUNCING sweeper's job, and it is
    enforcing-only by design.

    And it still CEDES an enforcing tenant's EMITTED work to reap_stale_tasks,
    which announces the stop to the tenant's workers; never-emitted
    (last_event_at IS NULL) work stays eligible here — the original safety net,
    and for enforcing tenants it frees the concurrency slot early.

    ⚠ THE CEDE IS ABOUT THE ANNOUNCEMENT, NOT THE STATE. Both sweepers write
    `expired`, so which one wins the race no longer decides what the row says —
    it decides only whether the tenant's idle workers are told. That is a
    narrower reason for the cede than the one it replaces, and it is the real
    one: the deterministic-terminal-state argument was solving a problem the
    six states delete.

    ⚠ PER TENANT RATHER THAN ONE SWEEP, because a window that belongs to a kind
    of work cannot be expressed as one pair of cutoffs over every tenant's
    table at once. It is the shape reap_stale_tasks already had, and the row
    set each pass reads is the same one a single query would have read.
    """
    from apps.platform.tenants.models import Tenant
    from apps.platform.work.models import Task
    from apps.platform.work.queries import expiry_windows
    from apps.platform.work.services import TaskService

    now = timezone.now()
    abandoned_cutoff = now - timedelta(hours=1)
    expired_count = 0

    for tenant in Tenant.objects.iterator():
        candidates = Task.objects.filter(tenant=tenant,
                                         status=TASK_STATUS_ACTIVE,
                                         created_at__lt=abandoned_cutoff)
        if tenant.enforcement_mode == "enforcing":
            candidates = candidates.filter(last_event_at__isnull=True)
        else:
            windows = expiry_windows(tenant.id)
            candidates = candidates.filter(
                Q(last_event_at__isnull=True) | _past_a_window(windows, now))

        for task in candidates.iterator():
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

    A unit that emitted events then went quiet for longer than its silence
    window, or any unit past its absolute deadline, is expired and a
    task.limit_exceeded event (subtask.limit_exceeded for stale contained work,
    expired alone) is emitted so sibling/idle workers tear down. Reaping a
    parent cascades the expiry to its active contained work (#38) — note a
    parent whose contained work is still emitting is never silent, since
    rollup stamps the parent's heartbeat too.

    ⚠ IT USED TO WRITE `killed` (#408), which meant the same silence was
    recorded two ways — this sweeper's `killed` and the other's `completed` —
    and left `killed` unable to answer *how often do we blow ceilings* without
    filtering on a reason string first. Both of this module's sweepers converge
    on `expired`.

    ⚠ BOTH WINDOWS NOW BELONG TO THE KIND OF WORK FIRST (#412). Each climbs the
    same three-rung ladder — the declared kind of work, then the tenant's own
    default, then UBB's backstop — so one kind of job that legitimately runs
    twenty minutes between reports no longer forces its sibling's window open
    too. What is NOT here, deliberately, is a keepalive: liveness is proved by
    reporting usage and by nothing else, and no read of a unit extends its
    life. An implicit keepalive on reads was rejected outright — a console
    listing, a support query or an admin inspecting stopped work would
    silently resurrect it.

    ⚠ AND AN ACCEPTED CONSEQUENCE THAT MUST STAY VISIBLE: an expiry can strike
    live work that is doing something long and atomic. That is not a failure
    and must not be counted as one; the console half of saying so is its own
    ticket.

    Enforcing-only: off tenants keep only the baseline close_abandoned_tasks
    (the silent >1h expiry, unannounced). Work that NEVER emitted is left to
    close_abandoned_tasks — silence is measured from the last report, and a
    unit that has never made one is slow to start rather than quiet. The
    winning transition (inside expire_and_announce) guards against
    double-emit.
    """
    from apps.platform.work.models import Task
    from apps.platform.work.queries import expiry_windows
    from apps.platform.work.services import TaskService
    from apps.platform.tenants.models import Tenant
    from apps.platform.tenants.flags import enforcing

    now = timezone.now()
    reaped = 0

    for tenant in Tenant.objects.filter(enforcement_mode="enforcing").iterator():
        if not enforcing(tenant):  # defensive: honor the single flag helper
            continue
        windows = expiry_windows(tenant.id)
        candidates = (Task.objects.filter(tenant=tenant,
                                          status=TASK_STATUS_ACTIVE)
                      .filter(_past_a_window(windows, now)))
        for task in candidates.iterator():
            # created_at is immutable and the declared kind with it, so the
            # reason is stable across the unlocked candidate read;
            # expire_and_announce owns the winning transition, the downward
            # cascade, the two-altitude event split, and the exactly-once emit.
            reason = _reason_for(task, windows, now)
            if TaskService.expire_and_announce(
                    task.id, reason,
                    tenant_id=tenant.id, customer_id=task.customer_id,
                    # WHICH MECHANISM APPLIED THIS STOP (#412), beside which
                    # window ran out. Both windows are this sweeper's, so one
                    # mechanism covers both reasons — which is exactly why the
                    # two are separate fields rather than one.
                    trigger_source=TRIGGER_SOURCE_STALE_REAPER):
                reaped += 1

    if reaped:
        logger.info("Reaped %d stale tasks", reaped)
    return reaped
