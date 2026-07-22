from django.core.cache import cache

from apps.billing.gating.crossing import past_floor
from apps.billing.gating.models import RiskConfig


class RiskService:
    @staticmethod
    def check(customer, create_task=False, task_metadata=None, external_task_id="",
              provider_cost_limit_micros=None, parent_task_id=None):
        from apps.billing.accounts import resolve_billing_owner
        owner = resolve_billing_owner(customer)
        # Status: gate if the seat OR its billing-owner (business) is suspended/closed
        for who in ([customer] if owner.id == customer.id else [customer, owner]):
            if who.status == "suspended":
                return {"allowed": False, "reason": "insufficient_funds", "balance_micros": None, "task_id": None}
            if who.status == "closed":
                return {"allowed": False, "reason": "account_closed", "balance_micros": None, "task_id": None}
        # Tier-2 P6: honor the synchronous customer-wide stop flag at the
        # start-gate (enforcing only — the flag cannot exist for an off
        # tenant) so a flag-stopped owner's NEW tasks are blocked even before
        # the durable suspend lands, and for postpaid owner-aggregate stops.
        from apps.platform.tenants.flags import enforcing
        if enforcing(customer.tenant):
            from apps.billing.gating.services.live_ledger_service import LiveLedgerService
            if LiveLedgerService.read_stop(owner.id, customer.tenant)["stop"]:
                return {"allowed": False, "reason": "customer_stopped",
                        "balance_micros": None, "task_id": None}
        try:
            config = customer.tenant.risk_config
        except RiskConfig.DoesNotExist:
            config = None
        # Fixed-window rate limiting (per-seat; degrades gracefully if Redis is down)
        if config and config.max_requests_per_minute and config.max_requests_per_minute > 0:
            try:
                cache_key = f"ratelimit:{customer.id}:rpm"
                current_count = cache.get(cache_key, 0)
                if current_count >= config.max_requests_per_minute:
                    return {"allowed": False, "reason": "rate_limit_exceeded", "balance_micros": None, "task_id": None}
                try:
                    cache.incr(cache_key)
                except ValueError:
                    cache.set(cache_key, 1, timeout=60)
            except Exception:
                pass  # Degrade: skip rate limiting if cache is unavailable

        # Affordability check: read wallet from billing owner (business for pooled seat, else self)
        from apps.billing.wallets.models import Wallet
        try:
            balance = Wallet.objects.get(customer=owner).balance_micros
        except Wallet.DoesNotExist:
            balance = 0

        from apps.billing.queries import get_customer_min_balance
        threshold = get_customer_min_balance(owner.id, owner.tenant_id)
        if owner.tenant.billing_mode != "postpaid" and past_floor(balance, threshold):
            return {"allowed": False, "reason": "insufficient_funds", "balance_micros": balance, "task_id": None}

        # Soft floor (#40, spec §F): past the resolved wind-down line, NEW
        # TOP-LEVEL task starts are refused — running tasks may complete, so
        # a subtask start under a parent passes (a contained child of running
        # work is running work completing; the parent's own liveness is
        # validated by the registration block below). enforcing-only, like
        # every state change; the hard-floor refusal above wins below both
        # lines. Wallet-based, so postpaid has no soft floor.
        if (parent_task_id is None and enforcing(customer.tenant)
                and owner.tenant.billing_mode != "postpaid"):
            from apps.billing.queries import get_customer_soft_min_balance
            from apps.billing.gating.services.stop_signal_service import SOFT_FLOOR_REACHED
            soft = get_customer_soft_min_balance(owner.id, owner.tenant_id)
            if past_floor(balance, soft):
                return {"allowed": False, "reason": SOFT_FLOOR_REACHED,
                        "balance_micros": balance, "task_id": None}

        # Budget cap: checked per-seat (customer, not owner)
        from apps.billing.gating.services.budget_service import BudgetService
        budget = BudgetService.check(customer)
        if not budget["allowed"]:
            return {"allowed": False, "reason": budget["reason"],
                    "balance_micros": balance, "task_id": None}

        result = {"allowed": True, "reason": None, "balance_micros": balance, "task_id": None}

        # Optionally create a Task, snapshotting wallet balance and limits.
        # One atomic block: subtask registration (#38) locks the parent row,
        # serializing against a concurrent cascade kill/close — a subtask can
        # never be born under an already-terminal parent.
        if create_task:
            from django.db import transaction
            from apps.platform.tasks.models import Task
            with transaction.atomic():
                parent = None
                if parent_task_id is not None:
                    # Subtask registration (#38). Refusals are legitimate:
                    # they refuse work that hasn't happened, never a usage
                    # report. A missing/foreign parent reads as not-active
                    # (a task that doesn't exist here is not an active task);
                    # the depth refusal wins over status for an existing row
                    # (the structural error is the actionable one).
                    parent = Task.objects.select_for_update().filter(
                        id=parent_task_id, tenant=customer.tenant,
                        customer=customer).first()
                    if parent is None:
                        return {"allowed": False, "reason": "parent_task_not_active",
                                "balance_micros": balance, "task_id": None}
                    if parent.parent_id is not None:
                        # One containment level at launch: a subtask cannot
                        # parent another unit.
                        return {"allowed": False, "reason": "subtask_depth_exceeded",
                                "balance_micros": balance, "task_id": None}
                    if parent.status != "active":
                        return {"allowed": False, "reason": "parent_task_not_active",
                                "balance_micros": balance, "task_id": None}
                # Tier-2 P5 (D11/I6): per-owner concurrency cap (enforcing-only).
                # The "slot count" is simply the number of ACTIVE tasks for the
                # billing owner — accurate + leak-free (no Redis slot to leak); the
                # reaper frees capacity by terminating stale tasks. A pooled business
                # shares one cap because every seat's task pins it as billing owner.
                # Bounded over-admit on the read-then-create race is accepted.
                # Subtasks hold a slot like any other unit — a child is still
                # parallel work.
                from apps.platform.tenants.flags import enforcing
                # > 0 (not truthiness): 0/NULL = no concurrency cap, and a negative
                # mis-config can never block every task (mirrors the rpm > 0 guard).
                if (enforcing(customer.tenant) and config
                        and config.max_concurrent_requests and config.max_concurrent_requests > 0):
                    active_tasks = Task.objects.filter(
                        billing_owner_id=owner.id, status="active").count()
                    if active_tasks >= config.max_concurrent_requests:
                        return {"allowed": False, "reason": "concurrency_limit",
                                "balance_micros": balance, "task_id": None}
                # One-rule (#37): the limit is COGS-denominated — passed at
                # start, tenant default as fallback (#38: subtasks fall back
                # to the subtask default); absent both, the unit is uncapped
                # and no signal ever fires.
                if provider_cost_limit_micros is None and config is not None:
                    provider_cost_limit_micros = (
                        config.default_subtask_provider_cost_limit_micros
                        if parent is not None
                        else config.default_task_provider_cost_limit_micros)
                # Coverage gate (#28 decision 10): a COGS limit over uncovered
                # events would silently count 0 — starting a limited unit is
                # refused unless the tenant requires cost-card coverage,
                # subtask limits the same as task limits. A start-gate refusal
                # is legitimate: it refuses work that hasn't happened, never a
                # usage report.
                if (provider_cost_limit_micros is not None
                        and not customer.tenant.require_cost_card_coverage):
                    return {"allowed": False, "reason": "cost_coverage_required",
                            "balance_micros": balance, "task_id": None}
                from apps.billing.queries import get_billing_config
                from apps.platform.tasks.services import TaskService

                billing_config = get_billing_config(customer.tenant_id)
                task = TaskService.create_task(
                    tenant=customer.tenant,
                    customer=customer,
                    parent=parent,
                    balance_snapshot_micros=balance,
                    provider_cost_limit_micros=provider_cost_limit_micros,
                    floor_snapshot_micros=billing_config.default_task_floor_snapshot_micros,
                    metadata=task_metadata or {},
                    external_task_id=external_task_id,
                    # Tier-2 (D4/I6): pin the resolved billing owner on the task.
                    billing_owner_id=owner.id,
                )
            result["task_id"] = str(task.id)
            result["parent_task_id"] = str(parent.id) if parent else None
            result["provider_cost_limit_micros"] = task.provider_cost_limit_micros
            result["floor_snapshot_micros"] = task.floor_snapshot_micros

        return result
