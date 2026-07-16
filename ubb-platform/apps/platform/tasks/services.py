import logging

from django.utils import timezone

from apps.platform.tasks.models import Task

logger = logging.getLogger(__name__)


class TaskService:

    @staticmethod
    def create_task(tenant, customer, balance_snapshot_micros,
                    provider_cost_limit_micros=None, floor_snapshot_micros=None,
                    metadata=None, external_task_id="", billing_owner_id=None):
        """Create a Task, snapshotting limit config and wallet balance.

        Limits are passed explicitly by the caller (billing pre-check), which
        owns the explicit-or-tenant-default resolution and the cost-coverage
        gate. Tier-2 (D4): billing_owner_id is PINNED here
        (resolve_billing_owner) so the concurrency slot + reapers never
        re-resolve a re-parented owner. Must be called inside
        @transaction.atomic.
        """
        return Task.objects.create(
            tenant=tenant,
            customer=customer,
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
        provider, denominationally explicit), stamps the heartbeat, and
        returns ``(task, verdicts)`` where ``verdicts`` is a dict of crossing
        verdicts for the caller to turn into the kill flow + stop fields:

        - ``crossed_task_limit``: THIS call pushed the provider total past
          ``provider_cost_limit_micros`` while the task was still active.
          Only the provider (COGS) total races the limit — a billed total
          past it fires nothing.
        - ``crossed_floor_snapshot``: THIS call pushed the estimated balance
          (balance snapshot minus billed total — wallet-shaped, so billed)
          below ``floor_snapshot_micros`` while the task was still active.
        - ``task_not_active``: the task was already killed/completed/failed.
          The event still landed, billed, and counted into both totals.

        A non-active task keeps accumulating with no limit verdicts (the
        signal already fired; re-announcing every late event would be spam).
        Must be called inside @transaction.atomic; uses select_for_update.
        """
        qs = Task.objects.select_for_update()
        if tenant_id is not None:
            qs = qs.filter(tenant_id=tenant_id)
        if customer_id is not None:
            qs = qs.filter(customer_id=customer_id)
        task = qs.get(id=task_id)

        was_active = task.status == "active"
        task.total_billed_cost_micros += int(billed_cost_micros)
        task.total_provider_cost_micros += int(provider_cost_micros)
        task.event_count += 1
        # Tier-2 (D10): stamp the heartbeat in the SAME write so the
        # stale-task reaper can tell a live task from a crashed one. This is
        # the single heartbeat-stamp site.
        task.last_event_at = timezone.now()
        task.save(update_fields=["total_billed_cost_micros",
                                 "total_provider_cost_micros", "event_count",
                                 "last_event_at", "updated_at"])

        verdicts = {
            "crossed_task_limit": False,
            "crossed_floor_snapshot": False,
            "task_not_active": not was_active,
        }
        if was_active:
            limit = task.provider_cost_limit_micros
            if limit is not None and task.total_provider_cost_micros > limit:
                verdicts["crossed_task_limit"] = True
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
        fan-out events (TaskLimitExceeded) exactly once even when racing.

        Killed is a signal point, not a wall: late events still land, bill,
        and count into the killed task's totals.

        Must be called inside @transaction.atomic.
        """
        qs = Task.objects.select_for_update()
        if tenant_id is not None:
            qs = qs.filter(tenant_id=tenant_id)
        if customer_id is not None:
            qs = qs.filter(customer_id=customer_id)
        task = qs.get(id=task_id)
        if task.status in ("killed", "completed", "failed"):
            return task, False
        task.status = "killed"
        task.completed_at = timezone.now()
        if reason:
            task.metadata = {**task.metadata, "kill_reason": reason}
        task.save(update_fields=["status", "completed_at", "metadata", "updated_at"])
        return task, True

    @staticmethod
    def kill_and_announce(task_id, reason, *, tenant_id, customer_id):
        """The idempotent kill flow: flip the task to killed and, ONLY on the
        winning active->killed transition, emit ``task.limit_exceeded`` — so
        racing callers (sync endpoint, batch items, async settle workers)
        can never double-emit.

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
        from apps.platform.events.schemas import TaskLimitExceeded
        try:
            with transaction.atomic():
                killed, transitioned = TaskService.kill_task(
                    task_id, reason=reason,
                    tenant_id=tenant_id, customer_id=customer_id)
                if transitioned:
                    write_event(TaskLimitExceeded(
                        tenant_id=str(tenant_id), customer_id=str(customer_id),
                        billing_owner_id=str(killed.billing_owner_id or ""),
                        task_id=str(killed.id),
                        external_task_id=killed.external_task_id,
                        reason=reason,
                        total_billed_cost_micros=killed.total_billed_cost_micros,
                        total_provider_cost_micros=killed.total_provider_cost_micros,
                        provider_cost_limit_micros=killed.provider_cost_limit_micros or 0))
            return transitioned
        except Exception:
            logger.exception("task.kill_failed", extra={"data": {
                "task_id": str(task_id), "tenant_id": str(tenant_id),
                "customer_id": str(customer_id), "reason": reason}})
            return False

    @staticmethod
    def complete_task(task_id):
        """Mark a task as completed. Idempotent — no-op if already in a terminal state.

        Must be called inside @transaction.atomic.
        """
        task = Task.objects.select_for_update().get(id=task_id)
        if task.status in ("killed", "completed", "failed"):
            return task
        task.status = "completed"
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "completed_at", "updated_at"])
        return task
