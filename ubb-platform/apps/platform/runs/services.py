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
    def create_run(tenant, customer, balance_snapshot_micros, metadata=None, external_run_id=""):
        """Create a Run, snapshotting the tenant's hard stop config and wallet balance.

        Must be called inside @transaction.atomic.
        """
        return Run.objects.create(
            tenant=tenant,
            customer=customer,
            balance_snapshot_micros=balance_snapshot_micros,
            cost_limit_micros=tenant.run_cost_limit_micros,
            hard_stop_balance_micros=tenant.hard_stop_balance_micros,
            metadata=metadata or {},
            external_run_id=external_run_id,
        )

    @staticmethod
    def accumulate_cost(run_id, cost_micros):
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
        run = Run.objects.select_for_update().get(id=run_id)

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

        # Under both limits — accumulate
        run.total_cost_micros = new_total
        run.event_count += 1
        run.save(update_fields=["total_cost_micros", "event_count", "updated_at"])
        return run

    @staticmethod
    def kill_run(run_id, reason=""):
        """Mark a run as killed. Idempotent — no-op if already in a terminal state.

        Must be called inside @transaction.atomic.
        """
        run = Run.objects.select_for_update().get(id=run_id)
        if run.status in ("killed", "completed", "failed"):
            return run
        run.status = "killed"
        run.completed_at = timezone.now()
        if reason:
            run.metadata = {**run.metadata, "kill_reason": reason}
        run.save(update_fields=["status", "completed_at", "metadata", "updated_at"])
        return run

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
