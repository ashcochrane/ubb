import logging

from django.utils import timezone

from apps.platform.runs.models import Run

logger = logging.getLogger(__name__)


class HardStopExceeded(Exception):
    """Raised when a run's accumulated cost would exceed a hard stop limit."""

    def __init__(self, run_id, reason, total_cost_micros, estimated_balance):
        self.run_id = str(run_id)
        self.reason = reason
        self.total_cost_micros = total_cost_micros
        self.estimated_balance = estimated_balance
        super().__init__(
            f"Run {run_id} hard stop: {reason} "
            f"(cost={total_cost_micros}, est_balance={estimated_balance})"
        )


class RunNotActive(Exception):
    """Raised when an operation is attempted on a non-active run."""

    def __init__(self, run_id, status):
        self.run_id = str(run_id)
        self.status = status
        super().__init__(f"Run {run_id} is not active (status={status})")


class RunService:

    @staticmethod
    def create_run(tenant, customer, balance_snapshot_micros,
                   cost_limit_micros=None, hard_stop_balance_micros=None,
                   metadata=None, external_run_id="", billing_owner_id=None):
        """Create a Run, snapshotting hard stop config and wallet balance.

        Limits are passed explicitly by the caller (billing pre-check).
        Tier-2 (D4): billing_owner_id is PINNED here (resolve_billing_owner)
        so the concurrency slot + reapers never re-resolve a re-parented owner.
        Must be called inside @transaction.atomic.
        """
        return Run.objects.create(
            tenant=tenant,
            customer=customer,
            balance_snapshot_micros=balance_snapshot_micros,
            cost_limit_micros=cost_limit_micros,
            hard_stop_balance_micros=hard_stop_balance_micros,
            metadata=metadata or {},
            external_run_id=external_run_id,
            billing_owner_id=billing_owner_id,
        )

    @staticmethod
    def accumulate_cost(run_id, cost_micros, *, tenant_id=None, customer_id=None):
        """Atomically accumulate cost on a run and check both hard stop conditions.

        Must be called inside @transaction.atomic.
        Uses select_for_update to prevent race conditions.

        Returns the locked Run instance on success.

        Raises RunNotActive if the run is not in "active" status.
        Raises HardStopExceeded if either:
          1. total_cost + cost > cost_limit_micros (per-run ceiling)
          2. balance_snapshot - (total_cost + cost) < hard_stop_balance_micros (wallet floor)

        On failure, the Run is NOT modified — the caller handles killing it
        in a separate transaction after the outer @transaction.atomic rolls back.
        """
        qs = Run.objects.select_for_update()
        if tenant_id is not None:
            qs = qs.filter(tenant_id=tenant_id)
        if customer_id is not None:
            qs = qs.filter(customer_id=customer_id)
        run = qs.get(id=run_id)

        if run.status != "active":
            raise RunNotActive(run_id=str(run.id), status=run.status)

        new_total = run.total_cost_micros + cost_micros
        estimated_balance = run.balance_snapshot_micros - new_total

        # Check 1: per-run cost ceiling
        if run.cost_limit_micros is not None and new_total > run.cost_limit_micros:
            raise HardStopExceeded(
                run_id=str(run.id),
                reason="cost_limit_exceeded",
                total_cost_micros=new_total,
                estimated_balance=estimated_balance,
            )

        # Check 2: wallet balance floor
        if run.hard_stop_balance_micros is not None and estimated_balance < run.hard_stop_balance_micros:
            raise HardStopExceeded(
                run_id=str(run.id),
                reason="balance_floor_exceeded",
                total_cost_micros=new_total,
                estimated_balance=estimated_balance,
            )

        # Under both limits — accumulate. Tier-2 (D10): stamp the heartbeat in
        # the SAME write so the stale-run reaper can tell a live run from a
        # crashed one. This is the single heartbeat-stamp site.
        run.total_cost_micros = new_total
        run.event_count += 1
        run.last_event_at = timezone.now()
        run.save(update_fields=["total_cost_micros", "event_count",
                                "last_event_at", "updated_at"])
        return run

    @staticmethod
    def accumulate_cost_settled(run_id, cost_micros, *, tenant_id=None, customer_id=None):
        """Settlement-path cost accumulation (Task 6: async ingest settle_raw).

        Same row lock + heartbeat stamp as accumulate_cost, but deliberately
        carries NO limit checks and TOLERATES a non-active run: enforcement
        already happened at accept time (the estimate hold gate), so a settle
        that lands after the run was killed/completed must still record the
        TRUE cost against the run's total — never raise, never roll back the
        settle. Must be called inside @transaction.atomic.
        """
        qs = Run.objects.select_for_update()
        if tenant_id is not None:
            qs = qs.filter(tenant_id=tenant_id)
        if customer_id is not None:
            qs = qs.filter(customer_id=customer_id)
        run = qs.get(id=run_id)

        run.total_cost_micros = run.total_cost_micros + cost_micros
        run.event_count += 1
        run.last_event_at = timezone.now()
        run.save(update_fields=["total_cost_micros", "event_count",
                                "last_event_at", "updated_at"])
        return run

    @staticmethod
    def kill_run(run_id, reason="", *, tenant_id=None, customer_id=None):
        """Mark a run as killed. Idempotent — no-op if already in a terminal
        state. Returns (run, transitioned): transitioned is True iff THIS
        call performed the active->killed transition, so callers can emit
        fan-out events (RunLimitExceeded) exactly once even when racing.

        Must be called inside @transaction.atomic.
        """
        qs = Run.objects.select_for_update()
        if tenant_id is not None:
            qs = qs.filter(tenant_id=tenant_id)
        if customer_id is not None:
            qs = qs.filter(customer_id=customer_id)
        run = qs.get(id=run_id)
        if run.status in ("killed", "completed", "failed"):
            return run, False
        run.status = "killed"
        run.completed_at = timezone.now()
        if reason:
            run.metadata = {**run.metadata, "kill_reason": reason}
        run.save(update_fields=["status", "completed_at", "metadata", "updated_at"])
        return run, True

    @staticmethod
    def complete_run(run_id):
        """Mark a run as completed. Idempotent — no-op if already in a terminal state.

        Must be called inside @transaction.atomic.
        """
        run = Run.objects.select_for_update().get(id=run_id)
        if run.status in ("killed", "completed", "failed"):
            return run
        run.status = "completed"
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "completed_at", "updated_at"])
        return run
