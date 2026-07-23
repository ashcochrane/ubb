"""The hourly patrol — emission + delivery guaranteed independent of traffic
(#44, delivery spec §C/§F).

Late, never lost: a real crossing always eventually produces its signal, and
an emitted signal always eventually reaches the tenant, no matter what
crashed at the moment of detection or how long the tenant's endpoint was
down. The jobs here join the existing hourly reconcile pass
(``reconcile_live_ledgers`` — no new scheduled task; enforcing tenants only):

1. Missed-transition drive + fast-flag re-alignment run PER OWNER inside
   ``LiveCounter.reconcile`` (§C.1/§C.2) — this module receives their
   flag-realignment count for the outcome record.
2. ``remint_unannounced_signals`` (§C.3) — any signal-ledger row whose last
   announcement never terminally succeeded gets a fresh CURRENT-STATE event
   (``re_announcement: true``, current episode), through the same atomic
   emit+stamp unit as a live transition. Bottom-line only by construction:
   the stamp always points at the LAST announcement, so an intermediate flap
   that was superseded is never replayed.
3. ``sweep_over_limit_tasks`` + ``remint_unannounced_kills`` (§C.4) — active
   tasks sitting at-or-past their provider-cost limit are swept into the
   idempotent kill flow; killed-but-unannounced tasks are re-minted.
4. Upward live-balance repair (§D, #45) — ``apps.billing.gating.repair``:
   the grace-gated honesty repair of the prepaid live counter (candidate on
   one pass, min-of-two-measurements relative increment on the next), with
   its repaired/amount/lapsed outcomes folded into the same record.

Outcomes are recorded as day-bucketed ``PatrolOutcome`` counters for the
ops/ingest-health surface (§F). The shared outbox retry policy and the
dead-letter CRITICAL alert are untouched for every product — the patrol
re-mints AROUND a dead-lettered row, never mutates it. Worst-case emission
latency after a crash: one patrol interval plus the delivery retry schedule.
"""
import logging

from django.db import transaction
from django.db.models import Exists, F, OuterRef
from django.utils import timezone

logger = logging.getLogger("ubb.billing")

OUTCOME_REMINTED = "reminted"
OUTCOME_FLAG_REALIGNED = "flag_realigned"
OUTCOME_SWEEP_KILLED = "sweep_killed"
# Upward live-balance repair (§D, #45): repairs applied, micros applied (the
# repaired_micros bucket's count IS the amount), and lapsed candidates.
OUTCOME_REPAIRED = "repaired"
OUTCOME_REPAIRED_MICROS = "repaired_micros"
OUTCOME_REPAIR_LAPSED = "repair_lapsed"


def run_patrol(tenant, *, flag_realigned=0):
    """Run the tenant-level patrol jobs (after the per-owner reconcile loop)
    and record every outcome. ``flag_realigned`` is the count the per-owner
    reconcile passes already collected. Each job is isolated — one failing
    leg never blocks the others. Returns the outcome counts."""
    from apps.billing.gating import repair

    counts = {OUTCOME_FLAG_REALIGNED: flag_realigned,
              OUTCOME_REMINTED: 0, OUTCOME_SWEEP_KILLED: 0,
              OUTCOME_REPAIRED: 0, OUTCOME_REPAIRED_MICROS: 0,
              OUTCOME_REPAIR_LAPSED: 0}
    for outcome, job in ((OUTCOME_REMINTED, remint_unannounced_signals),
                         (OUTCOME_SWEEP_KILLED, sweep_over_limit_tasks),
                         (OUTCOME_REMINTED, remint_unannounced_kills)):
        try:
            counts[outcome] += job(tenant)
        except Exception:
            logger.exception("patrol.job_failed", extra={"data": {
                "tenant_id": str(tenant.id), "job": job.__name__}})
    # Job 5 — upward live-balance repair (§D, #45); multi-outcome record.
    try:
        for outcome, n in repair.repair_live_balances(tenant).items():
            counts[outcome] += n
    except Exception:
        logger.exception("patrol.job_failed", extra={"data": {
            "tenant_id": str(tenant.id), "job": "repair_live_balances"}})
    try:
        record_outcomes(tenant, counts)
    except Exception:
        logger.exception("patrol.record_failed",
                         extra={"data": {"tenant_id": str(tenant.id)}})
    if any(counts.values()):
        logger.info("patrol.outcomes", extra={"data": {
            "tenant_id": str(tenant.id), **counts}})
    return counts


def remint_unannounced_signals(tenant):
    """§C.3 — re-mint every unannounced signal-ledger row as a fresh
    current-state event and move its stamp, one row per atomic unit.

    UNANNOUNCED (see ``apps.platform.events.announcements``) = stamp null or
    terminally failed; a ``pending``/``processing`` stamp is in flight and
    left alone (at most one live announcement per row). The classification
    is re-checked under the row lock so a racing transition (which moves the
    stamp) wins cleanly. Rows silently closed by an enforcement-mode
    transition are skipped: that close never rides the wire (a config flip
    is not a re-cross), so there is nothing to announce.
    """
    from apps.billing.gating.models import StopSignalState
    from apps.platform.events.announcements import UNANNOUNCED, announcement_status

    reminted = 0
    for row_id in StopSignalState.objects.filter(
            tenant_id=tenant.id).values_list("id", flat=True):
        try:
            with transaction.atomic():
                row = StopSignalState.objects.select_for_update().get(id=row_id)
                if _administratively_closed(row):
                    continue
                if announcement_status(row.announce_outbox_id) != UNANNOUNCED:
                    continue
                _remint_signal_row(row, tenant)
                reminted += 1
        except Exception:
            logger.exception("patrol.remint_signal_failed", extra={"data": {
                "tenant_id": str(tenant.id), "row_id": str(row_id)}})
    return reminted


def _administratively_closed(row):
    from apps.billing.gating.services.stop_signal_service import (
        CLEAR_ENFORCEMENT_MODE_TRANSITION, STATE_CLEARED)
    return (row.state == STATE_CLEARED
            and row.reason == CLEAR_ENFORCEMENT_MODE_TRANSITION)


def _remint_signal_row(row, tenant):
    """Mint the row's current state as an ordinary event of the same catalog
    type — current ``episode_seq``, ``re_announcement: true`` — and stamp it,
    inside the caller's transaction (the §B atomic unit)."""
    from apps.billing.gating.services.stop_signal_service import (
        FAMILY_FLOOR_STOP, STATE_STOPPED, emit_stamped)
    from apps.billing.queries import get_customer_soft_min_balance
    from apps.platform.events.schemas import (
        SoftFloorCleared, SoftFloorCrossed, StopCleared, StopFired)

    balance = _owner_balance(row.owner_id, tenant)
    if row.family == FAMILY_FLOOR_STOP:
        if row.state == STATE_STOPPED:
            schema = StopFired(
                tenant_id=str(tenant.id), owner_id=str(row.owner_id),
                reason=row.reason, scope="customer",
                episode_seq=row.episode_seq, re_announcement=True)
        else:
            schema = StopCleared(
                tenant_id=str(tenant.id), owner_id=str(row.owner_id),
                reason=row.reason, scope="customer",
                episode_seq=row.episode_seq, balance_micros=balance,
                re_announcement=True)
    else:
        soft = get_customer_soft_min_balance(row.owner_id, tenant.id)
        if row.state == STATE_STOPPED:
            schema = SoftFloorCrossed(
                tenant_id=str(tenant.id), owner_id=str(row.owner_id),
                balance_micros=balance,
                soft_min_balance_micros=soft or 0,
                episode_seq=row.episode_seq, re_announcement=True)
        else:
            schema = SoftFloorCleared(
                tenant_id=str(tenant.id), owner_id=str(row.owner_id),
                reason=row.reason, balance_micros=balance,
                soft_min_balance_micros=soft,
                episode_seq=row.episode_seq, re_announcement=True)
    emit_stamped(row, schema)


def _owner_balance(owner_id, tenant):
    """The current durable balance riding a re-mint's balance field — the
    honest CURRENT-state view (postpaid has no spendable balance: 0)."""
    from apps.billing.queries import get_customer_balance
    if tenant.billing_mode == "postpaid":
        return 0
    return int(get_customer_balance(owner_id))


def sweep_over_limit_tasks(tenant):
    """§C.4 — sweep active tasks sitting at-or-past their provider-cost
    limit into the idempotent kill flow, so a kill transaction that crashed
    is retried within one interval even if the tenant's traffic never
    resumes. Rides the partial index on active limited tasks; the winning
    transition inside ``kill_and_announce`` keeps racing lanes exactly-once.
    A subtask over its OWN limit is killed alone; a parent's kill cascades
    downward as ever."""
    from apps.platform.tasks.models import Task
    from apps.platform.tasks.reasons import SUBTASK_LIMIT, TASK_LIMIT
    from apps.platform.tasks.services import TaskService

    swept = 0
    over = Task.objects.filter(
        tenant=tenant, status="active",
        provider_cost_limit_micros__isnull=False,
        total_provider_cost_micros__gte=F("provider_cost_limit_micros"))
    for task in over.iterator():
        reason = SUBTASK_LIMIT if task.parent_id is not None else TASK_LIMIT
        # kill_and_announce never raises; a lost race (already terminal)
        # returns False and is simply not counted.
        if TaskService.kill_and_announce(task.id, reason, tenant_id=tenant.id,
                                         customer_id=task.customer_id):
            swept += 1
    return swept


def remint_unannounced_kills(tenant):
    """§C.4 — re-mint killed tasks whose kill announcement dead-lettered.

    Only STAMPED kills qualify: a killed task with a null stamp is silent by
    design (a cascaded child, whose parent's event was the one signal) — the
    null-stamp-unannounced case cannot arise for tasks because the winning
    flip, the event, and the stamp commit in one transaction. The SQL
    prefilter (stamp points at a terminally failed outbox row) is an
    optimization; the shared classifier re-checks under the row lock.
    """
    from apps.platform.events.announcements import UNANNOUNCED, announcement_status
    from apps.platform.events.models import OutboxEvent
    from apps.platform.tasks.models import Task

    dead_stamp = OutboxEvent.objects.filter(
        id=OuterRef("announce_outbox_id"), status="failed")
    candidates = (Task.objects
                  .filter(tenant=tenant, status="killed",
                          announce_outbox_id__isnull=False)
                  .filter(Exists(dead_stamp))
                  .values_list("id", flat=True))
    reminted = 0
    for task_id in candidates:
        try:
            with transaction.atomic():
                task = Task.objects.select_for_update().get(id=task_id)
                if announcement_status(task.announce_outbox_id) != UNANNOUNCED:
                    continue
                _remint_kill(task, tenant)
                reminted += 1
        except Exception:
            logger.exception("patrol.remint_kill_failed", extra={"data": {
                "tenant_id": str(tenant.id), "task_id": str(task_id)}})
    return reminted


def _remint_kill(task, tenant):
    """Mint the killed unit's current state — same catalog type as the
    original kill event, current totals, ``re_announcement: true`` — and
    move the stamp, inside the caller's transaction."""
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import (
        SubtaskLimitExceeded, TaskLimitExceeded)

    common = dict(
        tenant_id=str(tenant.id), customer_id=str(task.customer_id),
        billing_owner_id=str(task.billing_owner_id or ""),
        external_task_id=task.external_task_id,
        reason=task.metadata.get("kill_reason", ""),
        total_billed_cost_micros=task.total_billed_cost_micros,
        total_provider_cost_micros=task.total_provider_cost_micros,
        provider_cost_limit_micros=task.provider_cost_limit_micros or 0,
        re_announcement=True)
    if task.parent_id is not None:
        outbox = write_event(SubtaskLimitExceeded(
            subtask_id=str(task.id), parent_task_id=str(task.parent_id),
            **common))
    else:
        outbox = write_event(TaskLimitExceeded(task_id=str(task.id), **common))
    task.announce_outbox_id = outbox.id
    task.save(update_fields=["announce_outbox_id", "updated_at"])


def record_outcomes(tenant, counts):
    """Fold this pass's nonzero outcome counts into the day-bucketed
    ``PatrolOutcome`` counters (the §F ops surface). ``get_or_create`` +
    F-increment: race-safe against a concurrent pass, no lost counts."""
    from apps.billing.gating.models import PatrolOutcome

    day = timezone.now().date()
    for outcome, n in counts.items():
        if not n:
            continue
        obj, created = PatrolOutcome.objects.get_or_create(
            tenant=tenant, day=day, outcome=outcome, defaults={"count": n})
        if not created:
            PatrolOutcome.objects.filter(pk=obj.pk).update(
                count=F("count") + n)
