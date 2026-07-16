import logging

from django.utils import timezone

from apps.platform.tasks.models import Task

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = ("killed", "completed", "failed")


class TaskService:

    @staticmethod
    def create_task(tenant, customer, balance_snapshot_micros,
                    provider_cost_limit_micros=None, floor_snapshot_micros=None,
                    metadata=None, external_task_id="", billing_owner_id=None,
                    parent=None):
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
            floor_snapshot_micros=floor_snapshot_micros,
            metadata=metadata or {},
            external_task_id=external_task_id,
            billing_owner_id=billing_owner_id,
        )

    @staticmethod
    def accumulate_cost(task_id, *, billed_cost_micros, provider_cost_micros,
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
        - ``crossed_floor_snapshot``: THIS call pushed the named unit's
          estimated balance (balance snapshot minus billed total —
          wallet-shaped, so billed) below its own ``floor_snapshot_micros``
          while the unit was still active. Floor snapshots stay own-row;
          only the limit rolls up.
        - ``task_not_active``: the named unit was already
          killed/completed/failed. The event still landed, billed, and
          counted into both totals (and the parent's).

        A non-active unit keeps accumulating with no limit verdicts (the
        signal already fired; re-announcing every late event would be spam);
        likewise a non-active parent accepts rollup silently.

        Lock ordering (see Task.parent): the immutable parent_id is read
        without a lock, then parent before child — the same order the
        cascade kill/close and subtask registration take, so rollup and
        cascade can never deadlock. Must be called inside
        @transaction.atomic; uses select_for_update.
        """
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
            unit.total_billed_cost_micros += int(billed_cost_micros)
            unit.total_provider_cost_micros += int(provider_cost_micros)
            unit.event_count += 1
            # Tier-2 (D10): stamp the heartbeat in the SAME write so the
            # stale-task reaper can tell a live task from a crashed one. A
            # subtask event stamps its parent too — a tree whose children
            # hum is alive.
            unit.last_event_at = now
            unit.save(update_fields=["total_billed_cost_micros",
                                     "total_provider_cost_micros",
                                     "event_count", "last_event_at",
                                     "updated_at"])

        def _crossed_limit(unit):
            limit = unit.provider_cost_limit_micros
            return limit is not None and unit.total_provider_cost_micros > limit

        was_active = task.status == "active"
        parent_was_active = parent is not None and parent.status == "active"
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
            "crossed_floor_snapshot": False,
            "task_not_active": not was_active,
        }
        if was_active:
            floor = task.floor_snapshot_micros
            if floor is not None and (task.balance_snapshot_micros
                                      - task.total_billed_cost_micros) < floor:
                verdicts["crossed_floor_snapshot"] = True
        return task, verdicts

    @staticmethod
    def kill_task(task_id, reason="", *, tenant_id=None, customer_id=None):
        """Mark a task as killed. Idempotent — no-op if already in a terminal
        state. Returns (task, transitioned): transitioned is True iff THIS
        call performed the active->killed transition, so callers can emit
        fan-out events (TaskLimitExceeded / SubtaskLimitExceeded) exactly
        once even when racing.

        Killing a PARENT cascades the flip downward to its active subtasks
        in the same transaction (containment cuts downward, never upward,
        #38) — cascaded flips are silent state changes carrying
        ``kill_reason=parent_killed``; the parent's event is the one signal.
        Only the winning transition cascades. Killing a subtask kills it
        ALONE — the parent keeps running and counting.

        Killed is a signal point, not a wall: late events still land, bill,
        and count into the killed unit's totals (and its parent's).

        Must be called inside @transaction.atomic. Lock order: parent before
        children (see Task.parent).
        """
        qs = Task.objects.select_for_update()
        if tenant_id is not None:
            qs = qs.filter(tenant_id=tenant_id)
        if customer_id is not None:
            qs = qs.filter(customer_id=customer_id)
        task = qs.get(id=task_id)
        if task.status in _TERMINAL_STATUSES:
            return task, False
        task.status = "killed"
        task.completed_at = timezone.now()
        if reason:
            task.metadata = {**task.metadata, "kill_reason": reason}
        task.save(update_fields=["status", "completed_at", "metadata", "updated_at"])
        if task.parent_id is None:
            TaskService._cascade(task, "killed")
        return task, True

    @staticmethod
    def _cascade(parent, status):
        """Flip the parent's still-active subtasks to ``status`` — the
        downward containment cut (#38). Runs inside the caller's transaction,
        after the parent's own winning flip (parent lock already held, so
        subtask registration — which locks the parent — can never slip a new
        child past a finished cascade)."""
        from apps.platform.tasks import reasons
        now = timezone.now()
        children = Task.objects.select_for_update().filter(
            parent=parent, status="active")
        for child in children:
            child.status = status
            child.completed_at = now
            update_fields = ["status", "completed_at", "updated_at"]
            if status == "killed":
                child.metadata = {**child.metadata,
                                  "kill_reason": reasons.PARENT_KILLED}
                update_fields.append("metadata")
            child.save(update_fields=update_fields)

    @staticmethod
    def kill_and_announce(task_id, reason, *, tenant_id, customer_id):
        """The idempotent kill flow: flip the unit to killed (cascading
        downward if it is a parent) and, ONLY on the winning active->killed
        transition, emit ``task.limit_exceeded`` — or, for a subtask,
        ``subtask.limit_exceeded`` scoped to it alone — so racing callers
        (sync endpoint, batch items, async settle workers, the reaper) can
        never double-emit.

        Runs in its OWN transaction: the event that tripped the limit is
        already committed (one-rule — the tipping event lands and bills), and
        the kill is a separate, replayable state change.

        NEVER raises: under 200-always a non-2xx must mean "this was not
        recorded", and the event WAS recorded — a kill failure is a loud log
        (the next event's verdict retries the kill), never a 5xx.
        Returns transitioned (bool).
        """
        from django.db import transaction
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import (
            SubtaskLimitExceeded, TaskLimitExceeded)
        try:
            with transaction.atomic():
                killed, transitioned = TaskService.kill_task(
                    task_id, reason=reason,
                    tenant_id=tenant_id, customer_id=customer_id)
                if transitioned:
                    common = dict(
                        tenant_id=str(tenant_id), customer_id=str(customer_id),
                        billing_owner_id=str(killed.billing_owner_id or ""),
                        external_task_id=killed.external_task_id,
                        reason=reason,
                        total_billed_cost_micros=killed.total_billed_cost_micros,
                        total_provider_cost_micros=killed.total_provider_cost_micros,
                        provider_cost_limit_micros=killed.provider_cost_limit_micros or 0)
                    if killed.parent_id is not None:
                        write_event(SubtaskLimitExceeded(
                            subtask_id=str(killed.id),
                            parent_task_id=str(killed.parent_id), **common))
                    else:
                        write_event(TaskLimitExceeded(
                            task_id=str(killed.id), **common))
            return transitioned
        except Exception:
            logger.exception("task.kill_failed", extra={"data": {
                "task_id": str(task_id), "tenant_id": str(tenant_id),
                "customer_id": str(customer_id), "reason": reason}})
            return False

    @staticmethod
    def complete_task(task_id):
        """Mark a task as completed. Idempotent — no-op if already in a
        terminal state. Returns (task, transitioned), mirroring kill_task.

        Completing a PARENT auto-completes its active subtasks in the same
        transaction (#38) — cleanup is one call; already-terminal subtasks
        (e.g. killed) keep their state. Completing a subtask completes it
        alone.

        Must be called inside @transaction.atomic.
        """
        task = Task.objects.select_for_update().get(id=task_id)
        if task.status in _TERMINAL_STATUSES:
            return task, False
        task.status = "completed"
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "completed_at", "updated_at"])
        if task.parent_id is None:
            TaskService._cascade(task, "completed")
        return task, True
