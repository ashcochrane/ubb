import logging

from django.utils import timezone

from core.amount_status_pairs import CUSTOMER_PRICE, SUPPLIER_COST
from core.cost_totals import counts_as_unresolved
from core.vocabulary import (
    COSTING_STATUS_KNOWN,
    PRICING_STATUS_KNOWN,
    TASK_STATUS_ACTIVE,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_EXPIRED,
    TASK_STATUS_KILLED,
)
from apps.platform.work.models import TERMINAL_TASK_STATUSES, Task

logger = logging.getLogger(__name__)


class TaskService:

    @staticmethod
    def create_task(tenant, customer, balance_snapshot_micros,
                    provider_cost_limit_micros=None,
                    metadata=None, external_task_id="", billing_owner_id=None,
                    parent=None, task_type="", dimension_slots=None):
        """Create a Task, snapshotting limit config and wallet balance.
        Passing ``parent`` registers a SUBTASK under it (#38) — a Task row
        with the self-FK set, one containment level at launch.

        Limits are passed explicitly by the caller (billing pre-check), which
        owns the explicit-or-tenant-default resolution, the cost-coverage
        gate, and the parent active/depth refusals; the depth guard here is
        defense in depth against internal misuse. Tier-2 (D4): billing_owner_id
        is PINNED here (resolve_billing_owner) so the concurrency slot +
        reapers never re-resolve a re-parented owner. Must be called inside
        @transaction.atomic.

        ``task_type`` and ``dimension_slots`` (design D7/D6) are pure
        pass-through: the caller (billing's start-gate) already resolved the
        declared kind of work and admitted the grouping field values —
        TaskService only writes what it is given. ``task_type`` is the whole
        declaration at EITHER altitude; ``parent`` is what says which.
        """
        if parent is not None and parent.parent_id is not None:
            raise ValueError(
                "subtask depth exceeded: a subtask cannot parent another "
                "task (one containment level at launch)")
        return Task.objects.create(
            tenant=tenant,
            customer=customer,
            parent=parent,
            balance_snapshot_micros=balance_snapshot_micros,
            provider_cost_limit_micros=provider_cost_limit_micros,
            metadata=metadata or {},
            external_task_id=external_task_id,
            billing_owner_id=billing_owner_id,
            task_type=task_type,
            **(dimension_slots or {}),
        )

    @staticmethod
    def accumulate_cost(task_id, *, billed_cost_micros, provider_cost_micros,
                        costing_status=COSTING_STATUS_KNOWN,
                        pricing_status=PRICING_STATUS_KNOWN,
                        tenant_id=None, customer_id=None):
        """The ONE accumulate primitive — always records, never raises on
        limits (one-rule: every event that reaches UBB is priced, recorded,
        and billed; limits are signal points, never billing walls).

        Atomically adds this event's costs to BOTH running totals (billed +
        provider, denominationally explicit), stamps the heartbeat, and — for
        a subtask — ROLLS the same costs up into its parent's totals and
        heartbeat in the same transaction (containment: the parent sees
        everything underneath it, #38). Rollup happens unconditionally: late
        events on a killed subtask keep counting into the parent.

        ``costing_status`` is the compute spine's own answer about the supplier
        cost (#328), and ``pricing_status`` its answer about the customer price
        (#351). Where either says the amount is unresolved, that total takes
        nothing and its own count takes one instead, so both totals this unit
        publishes are floors that say how much they left out. The rollup carries
        the counts upward like the money: a parent whose child excluded an
        amount has excluded it too.

        The two are kept apart all the way down. They are different events —
        a posting can carry a settled cost and an unresolved price — so a single
        status argument would have made one of the two totals lie on every event
        where they disagree.

        Returns ``(task, verdicts)`` where ``task`` is the named unit and
        ``verdicts`` is a dict of crossing verdicts for the caller to turn
        into the kill flow + stop fields (reasons.kill_plan / stop_fields):

        - ``crossed_task_limit``: THIS call pushed the governing TOP-LEVEL
          task's provider total past its ``provider_cost_limit_micros`` while
          that task was still active — the unit's own limit for a top-level
          event, the PARENT's limit (raced by the rolled-up total) for a
          subtask event. Only the provider (COGS) total races a limit — a
          billed total past it fires nothing.
        - ``crossed_subtask_limit``: THIS call pushed the subtask's own
          provider total past its own limit while the subtask was still
          active (always False for a top-level event).
        - ``task_not_active``: the named unit was already in one of the five
          terminal states. The event still landed, billed, and counted into
          both totals (and the parent's).

        A non-active unit keeps accumulating with no limit verdicts (the
        signal already fired; re-announcing every late event would be spam);
        likewise a non-active parent accepts rollup silently.

        Lock ordering (see Task.parent): the immutable parent_id is read
        without a lock, then parent before child — the same order the
        cascade kill/close and subtask registration take, so rollup and
        cascade can never deadlock. Must be called inside
        @transaction.atomic; uses select_for_update.
        """
        # A COST THAT IS ABSENT AND `known` IS A CONTRADICTION, AND THE DEFAULT
        # ABOVE IS WHY IT IS REFUSED HERE (#328). `costing_status` defaults to
        # `known` so the ~25 callers that pass a real amount need not restate
        # the obvious — but that same default would let a caller hand this seam
        # `None` with nothing said and have the exclusion silently vanish, which
        # is the "replaced by another default" this ticket exists to delete.
        # It is the posting table's own rule (`known` implies the amount is NOT
        # NULL), enforced where the accumulator can see it, because the total
        # this builds is written rather than re-read: an exclusion missed here
        # cannot be recovered later.
        if provider_cost_micros is None and costing_status == COSTING_STATUS_KNOWN:
            raise ValueError(
                "provider_cost_micros is None but costing_status says 'known': "
                "pass the spine's own status so the unit can count what it "
                "could not add")
        # The same refusal for the price half, and it is a SEPARATE statement
        # rather than one check over both pairs: a caller that got one right and
        # the other wrong must be told which, and a combined message would name
        # the pair it did not break as often as the one it did.
        if billed_cost_micros is None and pricing_status == PRICING_STATUS_KNOWN:
            raise ValueError(
                "billed_cost_micros is None but pricing_status says 'known': "
                "pass the spine's own status so the unit can count what it "
                "could not add")

        def _locked(unit_id):
            qs = Task.objects.select_for_update()
            if tenant_id is not None:
                qs = qs.filter(tenant_id=tenant_id)
            if customer_id is not None:
                qs = qs.filter(customer_id=customer_id)
            return qs.get(id=unit_id)

        # parent_id is immutable after creation, so this unlocked pre-read
        # can never go stale — it exists purely to know whether the parent
        # lock must be taken FIRST.
        parent_id = Task.objects.values_list(
            "parent_id", flat=True).get(id=task_id)
        parent = _locked(parent_id) if parent_id is not None else None
        task = _locked(task_id)

        now = timezone.now()

        def _add(unit):
            # AN UNRESOLVED CUSTOMER PRICE ADDS NOTHING AND IS COUNTED (#351),
            # on exactly the terms the supplier half below is. `int(None)` was
            # this line's failure shape — a `TypeError` inside the recording
            # path rather than a wrong number — from the moment the column went
            # nullable, and the status decides rather than the amount because
            # `waived` and `not_applicable` null it too and neither is missing.
            if billed_cost_micros is not None:
                unit.total_billed_cost_micros += int(billed_cost_micros)
            elif counts_as_unresolved(CUSTOMER_PRICE, pricing_status):
                unit.unpriced_event_count += 1
            # AN UNRESOLVED SUPPLIER COST ADDS NOTHING AND IS COUNTED, WHICH IS
            # WHAT MAKES THE TOTAL A FLOOR THAT SAYS SO (#320, #328). Before the
            # compute spine could say "UBB does not know what this cost",
            # `provider_cost_micros` was always a number and this line always
            # ran; now the recording path hands `None` for a posting whose cost
            # is unresolved, and adding a zero for it would be the silent-zero
            # this slice exists to delete — the unit total would read complete
            # while excluding a charge that really happened.
            #
            # THE STATUS DECIDES, NOT THE AMOUNT. A `None` arrives for an
            # unresolved cost and for one that does not exist, and only the
            # first is missing information: counting the second would mark every
            # metering-only tenant's every unit partial forever (#327). The
            # caller passes the spine's own answer rather than this seam
            # re-deriving one, because a second definition of "unresolved" is
            # how two of them come to disagree.
            #
            # The COGS limit below races the floor, which is the direction that
            # under-fires rather than over-fires: a unit is never killed for
            # spend UBB cannot demonstrate.
            if provider_cost_micros is not None:
                unit.total_provider_cost_micros += int(provider_cost_micros)
            elif counts_as_unresolved(SUPPLIER_COST, costing_status):
                unit.unresolved_event_count += 1
            unit.event_count += 1
            # Tier-2 (D10): stamp the heartbeat in the SAME write so the
            # stale-task reaper can tell a live task from a crashed one. A
            # subtask event stamps its parent too — a tree whose children
            # hum is alive.
            unit.last_event_at = now
            unit.save(update_fields=["total_billed_cost_micros",
                                     "unpriced_event_count",
                                     "total_provider_cost_micros",
                                     "unresolved_event_count",
                                     "event_count", "last_event_at",
                                     "updated_at"])

        def _crossed_limit(unit):
            limit = unit.provider_cost_limit_micros
            return limit is not None and unit.total_provider_cost_micros > limit

        was_active = task.status == TASK_STATUS_ACTIVE
        parent_was_active = (parent is not None
                             and parent.status == TASK_STATUS_ACTIVE)
        _add(task)
        if parent is not None:
            _add(parent)

        # The governing top-level task: the unit itself, or its parent.
        top = parent if parent is not None else task
        top_was_active = parent_was_active if parent is not None else was_active
        verdicts = {
            "crossed_task_limit": top_was_active and _crossed_limit(top),
            "crossed_subtask_limit": (parent is not None and was_active
                                      and _crossed_limit(task)),
            "task_not_active": not was_active,
        }
        return task, verdicts

    @staticmethod
    def _flip(task_id, status, *, cascade_to, reason="",
              tenant_id=None, customer_id=None):
        """THE ONE TERMINAL TRANSITION, and the one place terminality is
        enforced (#408). Returns ``(task, transitioned)``; ``transitioned`` is
        True iff THIS call performed the flip out of ``active``, so callers can
        do their exactly-once work — emit a fan-out event, stamp an
        announcement — even when racing.

        **Terminal to anything is never permitted**, which is why the recheck
        under the row lock lives here rather than once per entry point: three
        copies of a refusal is three chances for the fourth transition to
        arrive without one. A row already in a terminal state is returned
        untouched with ``transitioned=False`` — a no-op rather than an
        exception, because every caller is a retry-safe signal path and the
        losing lane of a race has nothing to apologise for.

        ``cascade_to`` is a SEPARATE argument from ``status`` and that is the
        whole of I1. Contained work the tenant said nothing about must not
        inherit a state that means *the tenant declared delivery*, so a close
        cascades `cancelled` while it writes `completed` on the unit whose
        delivery was actually declared. Where the two do coincide — a kill, an
        expiry — they are passed the same value on purpose, so the coincidence
        is stated rather than assumed.

        Only the winning transition cascades, and only from a top-level unit:
        flipping contained work flips it ALONE, and its parent keeps running
        and counting.

        A terminal state is a signal point, not a wall: late events still land,
        bill, and count into this unit's totals (and its parent's).

        Must be called inside @transaction.atomic. Lock order: parent before
        children (see Task.parent).
        """
        qs = Task.objects.select_for_update()
        if tenant_id is not None:
            qs = qs.filter(tenant_id=tenant_id)
        if customer_id is not None:
            qs = qs.filter(customer_id=customer_id)
        task = qs.get(id=task_id)
        if task.status in TERMINAL_TASK_STATUSES:
            return task, False
        task.status = status
        task.completed_at = timezone.now()
        update_fields = ["status", "completed_at", "updated_at"]
        if reason:
            task.metadata = {**task.metadata, "kill_reason": reason}
            update_fields.append("metadata")
        task.save(update_fields=update_fields)
        if task.parent_id is None:
            TaskService._cascade(task, cascade_to)
        return task, True

    @staticmethod
    def kill_task(task_id, reason="", *, tenant_id=None, customer_id=None):
        """UBB STOPPED THIS ON A SPEND SIGNAL, and nothing else writes
        `killed` (I2, spec §2). A ceiling crossing, the patrol, or — through
        the cascade below — a parent that crossed one.

        Nothing the tenant declares may land here: that keeps the past-limit
        report, the stop context and the announcement bookkeeping honest, and
        makes *how often do we blow ceilings* answerable without first
        filtering on a reason string.

        Killing a PARENT cascades the flip downward to its active subtasks in
        the same transaction (containment cuts downward, never upward, #38) —
        cascaded flips are silent state changes carrying
        ``kill_reason=parent_killed``; the parent's event is the one signal.
        """
        return TaskService._flip(
            task_id, TASK_STATUS_KILLED, cascade_to=TASK_STATUS_KILLED,
            reason=reason, tenant_id=tenant_id, customer_id=customer_id)

    @staticmethod
    def expire_task(task_id, reason="", *, tenant_id=None, customer_id=None):
        """NOBODY EVER TOLD UBB HOW THIS ENDED (spec §7). Both sweepers write
        it, and it is the honest answer the model could not give before: the
        crash sweeper used to write `completed` and stamp a marker in metadata,
        while the stale reaper wrote `killed` — the same silence recorded two
        ways, and the spend story dishonest in both directions.

        The cascade carries the same state, because a parent nobody reported on
        is a parent whose contained work nobody reported on either.
        """
        return TaskService._flip(
            task_id, TASK_STATUS_EXPIRED, cascade_to=TASK_STATUS_EXPIRED,
            reason=reason, tenant_id=tenant_id, customer_id=customer_id)

    @staticmethod
    def _cascade(parent, status):
        """Flip the parent's still-active subtasks to ``status`` — the
        downward containment cut (#38). Runs inside the caller's transaction,
        after the parent's own winning flip (parent lock already held, so
        subtask registration — which locks the parent — can never slip a new
        child past a finished cascade).

        ⚠ ONLY THE KILL CASCADE RECORDS A REASON, AND THE OTHER TWO OWE ONE.
        The registry names `outcome_reason: parent_closed` for a close cascade
        and `reason_code: silence_window` for an expiry cascade; each arrives
        with the ticket that wires its concept's consumers, because writing
        either here would put a value set this slice has not yet taken
        ownership of into a second place. The STATE is what this ticket owes
        and what it writes — a withdrawn piece of contained work is already
        distinguishable from a delivered one without the reason.
        """
        from apps.platform.work import reasons
        now = timezone.now()
        children = Task.objects.select_for_update().filter(
            parent=parent, status=TASK_STATUS_ACTIVE)
        for child in children:
            child.status = status
            child.completed_at = now
            update_fields = ["status", "completed_at", "updated_at"]
            if status == TASK_STATUS_KILLED:
                child.metadata = {**child.metadata,
                                  "kill_reason": reasons.PARENT_KILLED}
                update_fields.append("metadata")
            child.save(update_fields=update_fields)

    @staticmethod
    def kill_and_announce(task_id, reason, *, tenant_id, customer_id):
        """The idempotent kill flow: flip the unit to `killed` (cascading
        downward if it is a parent) and, ONLY on the winning transition, emit
        ``task.limit_exceeded`` — or, for contained work,
        ``subtask.limit_exceeded`` scoped to it alone — so racing callers
        (sync endpoint, batch items, async settle workers, the patrol) can
        never double-emit.

        This is the SPEND lane, and after #408 that is all it is: the callers
        left are the ones holding a crossing.
        """
        return TaskService._stop_and_announce(
            TaskService.kill_task, task_id, reason,
            tenant_id=tenant_id, customer_id=customer_id)

    @staticmethod
    def expire_and_announce(task_id, reason, *, tenant_id, customer_id):
        """The same flow for the state at the other end of §2's table: flip the
        unit to `expired` and announce it exactly once.

        ⚠ THE ANNOUNCEMENT IS UNCHANGED AND THE STATE IS NOT (#408). This lane
        announced before the six states existed — the reaper's stop is what
        tells a customer's idle workers to tear down — and taking the signal
        away would be a regression nothing asked for. So the event still says
        `limit_exceeded` while the row now says `expired`: an event named for a
        bound rather than for the state entered, which is an individually
        ledgered debt the terminal-event split pays by name. Recording the
        state honestly first is what makes that split expressible at all.
        """
        return TaskService._stop_and_announce(
            TaskService.expire_task, task_id, reason,
            tenant_id=tenant_id, customer_id=customer_id)

    @staticmethod
    def _stop_and_announce(flip, task_id, reason, *, tenant_id, customer_id):
        """Flip through ``flip`` and, on the winning transition only, emit the
        fan-out event and stamp the announcement id.

        Runs in its OWN transaction: the event that tripped the signal is
        already committed (one-rule — the tipping event lands and bills), and
        the stop is a separate, replayable state change.

        NEVER raises: under 200-always a non-2xx must mean "this was not
        recorded", and the event WAS recorded — a stop failure is a loud log
        (the next event's verdict retries it), never a 5xx.
        Returns transitioned (bool).
        """
        from django.db import transaction
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import (
            SubtaskLimitExceeded, TaskLimitExceeded)
        try:
            with transaction.atomic():
                stopped, transitioned = flip(
                    task_id, reason=reason,
                    tenant_id=tenant_id, customer_id=customer_id)
                if transitioned:
                    common = dict(
                        tenant_id=str(tenant_id), customer_id=str(customer_id),
                        billing_owner_id=str(stopped.billing_owner_id or ""),
                        external_task_id=stopped.external_task_id,
                        reason=reason,
                        total_billed_cost_micros=stopped.total_billed_cost_micros,
                        total_provider_cost_micros=stopped.total_provider_cost_micros,
                        # The total that crossed the limit is a floor when this
                        # is non-zero (#328) — the unit really spent at least
                        # that much, so the crossing is sound and understated.
                        unresolved_event_count=stopped.unresolved_event_count,
                        provider_cost_limit_micros=stopped.provider_cost_limit_micros or 0)
                    if stopped.parent_id is not None:
                        outbox = write_event(SubtaskLimitExceeded(
                            subtask_id=str(stopped.id),
                            parent_task_id=str(stopped.parent_id), **common))
                    else:
                        outbox = write_event(TaskLimitExceeded(
                            task_id=str(stopped.id), **common))
                    # Announcement bookkeeping (delivery spec §B, #43):
                    # stamp inside the same transaction as the flip + event —
                    # all three commit or vanish together.
                    stopped.announce_outbox_id = outbox.id
                    stopped.save(update_fields=["announce_outbox_id",
                                               "updated_at"])
            return transitioned
        except Exception:
            logger.exception("task.kill_failed", extra={"data": {
                "task_id": str(task_id), "tenant_id": str(tenant_id),
                "customer_id": str(customer_id), "reason": reason}})
            return False

    @staticmethod
    def complete_task(task_id):
        """THE TENANT DECLARED DELIVERY, and nothing else writes `completed`
        (I1, spec §2). An explicit close is the only writer — which is what
        makes the state safe for a charge to key on, and is exactly the
        property the model could not offer while a sweeper wrote it too.

        ⚠ THE CASCADE WITHDRAWS, IT DOES NOT DELIVER. Closing a PARENT flips
        its still-active contained work to `cancelled` in the same transaction
        (#38) — cleanup is still one call — because the tenant declared the
        delivery of the whole unit and declared nothing at all about each
        contained piece. Writing `completed` there would be UBB declaring a
        delivery on the tenant's behalf, which is the one thing `completed` may
        never mean. Already-terminal contained work keeps its state; closing
        contained work closes it alone.

        Must be called inside @transaction.atomic.
        """
        return TaskService._flip(
            task_id, TASK_STATUS_COMPLETED, cascade_to=TASK_STATUS_CANCELLED)
