"""The hourly patrol — emission + delivery guaranteed independent of traffic
(#44, delivery spec §C/§F).

Late, never lost: a real crossing always eventually produces its signal, and
an emitted signal always eventually reaches the tenant, no matter what
crashed at the moment of detection or how long the tenant's endpoint was
down. The jobs here join the existing hourly reconcile pass
(``reconcile_live_ledgers`` — no new scheduled task). Since #452 that pass
visits EVERY tenant: legs 1, 2 and 4 are the customer-wide family and run for
enforcing tenants only; leg 3 is the ceiling's repair and runs for all,
because declaring a ceiling is itself the opt-in (#150 §11.2) and the
recording lane stops on it whatever the switch says:

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
   idempotent kill flow; a stopped-but-unannounced unit is re-minted. The
   SWEEP is the spend lane and stops only on a crossing, so it writes `killed`
   alone; the RE-MINT follows the announcement stamp instead, so it covers
   `expired` as well — the reaper's stop is announced too (#408).
   ``sweep_pool_stopped_work`` (#459) is the same repair for the pool's
   kill: active work under an open pool line is swept into the kill flow,
   and it is customer-wide, so it runs with legs 1, 2 and 4.
4. Upward live-balance repair (§D, #45) — ``apps.billing.gating.repair``:
   the grace-gated honesty repair of the prepaid live counter (candidate on
   one pass, min-of-two-measurements relative increment on the next), with
   its repaired/amount/lapsed outcomes folded into the same record.

Outcomes are recorded as day-bucketed ``PatrolOutcome`` counters, read
through ``apps.billing.queries.get_patrol_stats`` (§F). The ops route that
used to serve them was deleted with the ingest pipeline it watched; the
counters and their read contract are unchanged. The shared outbox retry policy and the
dead-letter CRITICAL alert are untouched for every product — the patrol
re-mints AROUND a dead-lettered row, never mutates it. Worst-case emission
latency after a crash: one patrol interval plus the delivery retry schedule.
"""
import logging

from django.db import transaction
from django.db.models import Exists, F, OuterRef
from django.utils import timezone

from core.crossing import ceiling_reached_q
from core.vocabulary import (
    TASK_STATUS_ACTIVE, TASK_STATUS_EXPIRED, TASK_STATUS_KILLED,
    TRIGGER_SOURCE_ENFORCEMENT_PATROL)

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
    leg never blocks the others. Returns the outcome counts.

    ⚠ TWO OF THE LEGS RUN FOR EVERY TENANT AND THE REST FOR ENFORCING ONES
    (#452, slice 6 §3, §10). The ceiling is always on where declared — the
    recording lane stops a unit on it whatever ``enforcement_mode`` says — so
    the repair of a crashed ceiling stop (the sweep) and of a stopped unit's
    dead-lettered announcement (the kill re-mint) run for every tenant the
    beat visits. The signal-ledger re-mint and the live-balance repair are
    the customer-wide family, which the switch governs; an ``off`` tenant
    has no ledger rows to re-mint and no counter to repair, and saying so
    here is what keeps that a decision rather than a coincidence."""
    from apps.billing.gating import repair
    from apps.platform.tenants.flags import enforcing

    counts = {OUTCOME_FLAG_REALIGNED: flag_realigned,
              OUTCOME_REMINTED: 0, OUTCOME_SWEEP_KILLED: 0,
              OUTCOME_REPAIRED: 0, OUTCOME_REPAIRED_MICROS: 0,
              OUTCOME_REPAIR_LAPSED: 0}
    legs = [(OUTCOME_SWEEP_KILLED, sweep_over_limit_tasks),
            (OUTCOME_REMINTED, remint_unannounced_kills)]
    if enforcing(tenant):
        legs.insert(0, (OUTCOME_REMINTED, remint_unannounced_signals))
        legs.append((OUTCOME_SWEEP_KILLED, sweep_pool_stopped_work))
    for outcome, job in legs:
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
            and row.clear_reason == CLEAR_ENFORCEMENT_MODE_TRANSITION)


def _remint_signal_row(row, tenant):
    """Mint the row's current state as an ordinary event of the same catalog
    type — current ``episode_seq``, ``re_announcement: true`` — and stamp it,
    inside the caller's transaction (the §B atomic unit).

    ⚠ THE LINE, ITS FAMILY AND ITS CONTROL ARE READ OFF THE ROW (#458): a
    stop line's re-mint carries the line's word, the family the row is keyed
    by and the control id the episode recorded, exactly as the original
    announcement did; the patrol derives nothing and guesses nothing."""
    from apps.billing.gating.services.stop_signal_service import (
        STATE_STOPPED, STOP_LINES, control_fields, emit_stamped)
    from apps.billing.queries import get_customer_soft_min_balance
    from apps.platform.events.schemas import (
        SoftFloorCleared, SoftFloorCrossed, StopCleared, StopFired)

    balance = _owner_balance(row.owner_id, tenant)
    if row.reason in STOP_LINES:
        control = control_fields(row)
        if row.state == STATE_STOPPED:
            schema = StopFired(
                tenant_id=str(tenant.id), owner_id=str(row.owner_id),
                scope="customer", episode_seq=row.episode_seq,
                re_announcement=True, **control)
        else:
            schema = StopCleared(
                tenant_id=str(tenant.id), owner_id=str(row.owner_id),
                scope="customer", episode_seq=row.episode_seq,
                balance_micros=balance, re_announcement=True, **control)
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
                reason=row.clear_reason, balance_micros=balance,
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
    downward as ever.

    ⚠ THE COMPARISON IS AGAINST A FLOOR, AND THAT IS THE SAFE DIRECTION (#328).
    A unit's provider total excludes every cost UBB has not resolved, so a unit
    this sweep passes over may really be past its limit — the sweep UNDER-fires,
    never over-fires, and no unit is killed for spend UBB cannot demonstrate.
    Firing on the floor plus its unresolved count would mean killing work on a
    number nobody has stated, which is a worse trade than a late kill. What the
    tenant gets instead is the count itself, on every read of the unit and on
    the kill announcement, so a limit that has not fired is visibly not the same
    as one that has been shown to be safe."""
    from apps.platform.work.models import Task
    from apps.platform.work.reasons import TASK_COGS_CEILING
    from apps.platform.work.services import TaskService, ceiling_control_id

    swept = 0
    # THE ONE COMPARE in its queryset spelling (#452): the same `>=` the
    # recording lane applies to the row in hand, so this sweep can only ever
    # find what that lane failed to stop — never a unit it deliberately
    # passed over.
    over = Task.objects.filter(tenant=tenant, status=TASK_STATUS_ACTIVE).filter(
        ceiling_reached_q("total_provider_cost_micros",
                          "task_cogs_ceiling_micros"))
    for task in over.iterator():
        # ONE WORD AT EITHER ALTITUDE (slice 6 §7, #457): the unit's own
        # ceiling was reached, and which altitude it sits at travels as the
        # stop's scope, never as a second reason.
        #
        # kill_and_announce never raises; a lost race (already terminal)
        # returns False and is simply not counted.
        #
        # WHICH MECHANISM APPLIED THIS STOP (#412): the patrol found a unit
        # already over its ceiling that no usage report had stopped, so this
        # sweep is the mechanism and the ingest lane is not — a subscriber
        # alerting on ceiling crossings can tell a live trip from a repair
        # only because the two lanes say which they are.
        #
        # AND WHICH CONTROL (#458): the ceiling is the declaration the unit
        # runs under, resolved by the kernel's own helper — the caller
        # passes the id, the kernel stamps the family.
        if TaskService.kill_and_announce(
                task.id, TASK_COGS_CEILING, tenant_id=tenant.id,
                customer_id=task.customer_id,
                trigger_source=TRIGGER_SOURCE_ENFORCEMENT_PATROL,
                control_id=ceiling_control_id(task)):
            swept += 1
    return swept


def sweep_pool_stopped_work(tenant):
    """The pool's own sweep (slice 6 §4, #459): every active unit of a
    customer whose POOL line is open is swept into the idempotent kill flow
    — the pool's word, ``pool_crossing``, the control the episode recorded.
    The kill is registered on the crossing's commit; a process that died
    between the ledger transition and its callbacks left the customer
    suspended and its work running, and this leg is what makes that late
    rather than lost, exactly as the ceiling's sweep does for a crashed
    ceiling kill. Customer-wide, so enforcing tenants only. Returns how many
    pieces of work it stopped."""
    from apps.billing.gating.models import StopSignalState
    from apps.billing.gating.services.customer_spend_pool_service import (
        CustomerSpendPoolService)
    from apps.billing.gating.services.stop_signal_service import (
        LINE_CUSTOMER_SPEND_POOL, STATE_STOPPED)

    swept = 0
    for owner_id, control_id in (StopSignalState.objects
                                 .filter(tenant_id=tenant.id, state=STATE_STOPPED,
                                         reason=LINE_CUSTOMER_SPEND_POOL)
                                 .values_list("owner_id", "control_id")):
        swept += CustomerSpendPoolService.stop_active_work(owner_id, tenant, control_id)
    return swept


def remint_unannounced_kills(tenant):
    """§C.4 — re-mint a stopped unit whose announcement dead-lettered.

    Only STAMPED stops qualify: a stopped unit with a null stamp is silent by
    design (cascaded contained work, whose parent's event was the one signal) —
    the null-stamp-unannounced case cannot arise because the winning flip, the
    event, and the stamp commit in one transaction. The SQL prefilter (stamp
    points at a terminally failed outbox row) is an optimization; the shared
    classifier re-checks under the row lock.

    ⚠ THE STATE FILTER NAMES BOTH ANNOUNCED STOPS (#408). The stamp is what
    makes a row a candidate — it means UBB announced this and the delivery
    failed — and the reaper's stop now lands in `expired` rather than `killed`.
    Leaving the filter on the one state would have quietly stopped re-minting
    every silence-driven announcement, which is a signal lost with no gate to
    notice: the row would still carry a stamp pointing at a dead letter and
    nothing would ever look at it again.
    """
    from apps.platform.events.announcements import UNANNOUNCED, announcement_status
    from apps.platform.events.models import OutboxEvent
    from apps.platform.work.models import Task

    dead_stamp = OutboxEvent.objects.filter(
        id=OuterRef("announce_outbox_id"), status="failed")
    candidates = (Task.objects
                  .filter(tenant=tenant,
                          status__in=(TASK_STATUS_KILLED, TASK_STATUS_EXPIRED),
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
    """Mint the stopped unit's current state — the event its own row now
    names, current totals, ``re_announcement: true`` — and move the stamp,
    inside the caller's transaction.

    ⚠ THE STATE IS READ OFF THE ROW AND SO IS EVERYTHING ELSE. A re-mint
    repairs a delivery; it applies no transition of its own and remembers
    nothing about the one that was applied, so every fact it publishes has to
    come from the record. The unit is `killed` or `expired`, and since the four
    terminal events that is what chooses which one is sent (#140 §4.3) — a
    re-mint of a unit that expired says `*.expired`, not the event the original
    announcement happened to carry."""
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import terminal_stop_event
    from apps.platform.work.models import (
        STOP_CAUSE_KEY, STOP_CONTROL_FAMILY_KEY, STOP_CONTROL_ID_KEY,
        STOP_MECHANISM_KEY)

    announcement = terminal_stop_event(
        task.status, is_contained=task.parent_id is not None)
    common = dict(
        tenant_id=str(tenant.id), customer_id=str(task.customer_id),
        billing_owner_id=str(task.billing_owner_id or ""),
        external_task_id=task.external_task_id,
        reason_code=task.metadata.get(STOP_CAUSE_KEY, ""),
        # ⚠ AND THE CONTROL IS READ BACK TOO (#458): the family and the id the
        # stopping lane stamped on the row, and the basis derived off the
        # row's own cause — this patrol applied nothing and guesses nothing.
        control_family=task.metadata.get(STOP_CONTROL_FAMILY_KEY, ""),
        control_id=task.metadata.get(STOP_CONTROL_ID_KEY, ""),
        ceiling_basis=task.ceiling_basis,
        # ⚠ AND THE MECHANISM IS READ BACK RATHER THAN INVENTED — it is not
        # this patrol, which applied nothing. The lane that DID apply the stop
        # records itself on the row (`TaskService._stop_and_announce`, and
        # `_cascade` for a contained piece), so a repaired delivery names the
        # same mechanism the original did. Empty where the row holds none,
        # which is UBB declining to state one rather than guessing.
        trigger_source=task.metadata.get(STOP_MECHANISM_KEY, ""),
        total_billed_cost_micros=task.total_billed_cost_micros,
        total_provider_cost_micros=task.total_provider_cost_micros,
        # A re-mint publishes the unit's CURRENT state, so it publishes the
        # current completeness too (#328) — a repaired delivery that dropped the
        # caveat would say more than the original did.
        unresolved_event_count=task.unresolved_event_count,
        task_cogs_ceiling_micros=task.task_cogs_ceiling_micros or 0,
        re_announcement=True)
    if task.parent_id is not None:
        outbox = write_event(announcement(
            subtask_id=str(task.id), parent_task_id=str(task.parent_id),
            **common))
    else:
        outbox = write_event(announcement(task_id=str(task.id), **common))
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
