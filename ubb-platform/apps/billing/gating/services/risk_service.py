from django.core.cache import cache

from core.vocabulary import TASK_TYPE_KIND_SUBTASK, TASK_TYPE_KIND_TASK

from apps.billing.gating.crossing import past_floor
from apps.billing.gating.models import RiskConfig


class RiskService:
    @staticmethod
    def resolve_type_policy(tenant, *, task_type, dimensions,
                            requested_limit_micros, is_subtask):
        """Validate the declared kind of work + dimensions and resolve the
        ceiling.

        ``task_type`` is the caller's declared kind of work at EITHER altitude
        (#407): a unit of work declares its kind once, and whether it has a
        parent is what says which altitude it is at. ``is_subtask`` is that
        parent link, which is why the declaration this looks up is chosen by it
        and not by which of two fields the caller filled in.

        Precedence (design D7): caller request (only if <= the declared
        default) -> the declared default -> RiskConfig tenant default ->
        uncapped. Returns (key, slot_values, limit_micros); a None limit means
        "no type-level opinion" — the caller applies the existing RiskConfig
        fallback.
        """
        from apps.platform.grouping_fields.services import DimensionError, DimensionService
        from apps.platform.work.queries import task_type_policy

        kind = TASK_TYPE_KIND_SUBTASK if is_subtask else TASK_TYPE_KIND_TASK
        key = task_type or ""
        policy = None
        if key:
            policy = task_type_policy(tenant.id, key, kind)
            if policy is None:
                raise ValueError(f"{kind} type {key!r} is not declared")
            if policy["retired"]:
                raise ValueError(f"{kind} type {key!r} is retired")

        # ⚠ NOT THE SAME VOCABULARY AS `kind` ABOVE, though two of its words are
        # spelled the same and the condition is the same one. `kind` is the
        # registry's `task_type_kind` — two values, saying which altitude a
        # DECLARED KIND OF WORK is meant for. This is `GroupingField.scope` —
        # three values including `event`, saying where a grouping field's value
        # is SET and therefore how far down it is inherited (ADR-0005). Held as
        # literals because that concept has no registry seat to import from, and
        # left as its own line rather than aliased to `kind`: folding them
        # together would make one word of two facts, which is the collision
        # ADR-0006 §3 uses as its worked example.
        scope = "subtask" if is_subtask else "task"
        try:
            slot_values = DimensionService.admit(tenant, dimensions or {}, scope=scope)
        except DimensionError as exc:
            raise ValueError(str(exc)) from exc

        if policy:
            supplied = set((dimensions or {}).keys())
            missing = [d for d in policy["required_dimensions"] if d not in supplied]
            if missing:
                raise ValueError(
                    f"{kind} type {key!r} missing required grouping field(s): "
                    f"{missing}")

        type_default = policy["default_provider_cost_limit_micros"] if policy else None
        if requested_limit_micros is not None:
            if type_default is not None and requested_limit_micros > type_default:
                raise ValueError(
                    f"provider_cost_limit_micros {requested_limit_micros} exceeds "
                    f"the {kind} type ceiling {type_default}")
            limit = requested_limit_micros
        elif type_default is not None:
            limit = type_default
        else:
            limit = None  # the existing RiskConfig fallback applies downstream
        return key, slot_values, limit

    @staticmethod
    def check(customer, create_task=False, task_metadata=None, external_task_id="",
              provider_cost_limit_micros=None, parent_task_id=None,
              task_type=None, dimensions=None):
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
            from apps.billing.gating.services.live_counter import LiveCounter
            if LiveCounter.read(owner.id, customer.tenant)["stop"]:
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
            from apps.platform.work.models import Task
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
                # Design D7: the ceiling belongs to the declared KIND of work,
                # server-side — a caller may request lower, never higher.
                # Raises ValueError (caught by the endpoint) on an undeclared/
                # retired type, a missing required grouping field, or a request
                # above the type's ceiling.
                resolved_key, slot_values, provider_cost_limit_micros = (
                    RiskService.resolve_type_policy(
                        customer.tenant, task_type=task_type,
                        dimensions=dimensions,
                        requested_limit_micros=provider_cost_limit_micros,
                        is_subtask=parent is not None))
                # One-rule (#37): the limit is COGS-denominated — passed at
                # start (or resolved from the task type above), tenant default
                # as fallback (#38: subtasks fall back to the subtask
                # default); absent all three, the unit is uncapped and no
                # signal ever fires.
                if provider_cost_limit_micros is None and config is not None:
                    provider_cost_limit_micros = (
                        config.default_subtask_provider_cost_limit_micros
                        if parent is not None
                        else config.default_task_provider_cost_limit_micros)
                # NO COVERAGE GATE HERE, AND NOTHING REPLACES IT (#321). A
                # limited unit used to be refused unless the tenant had set a
                # flag promising full cost coverage (#28 decision 10): a COGS
                # ceiling over uncovered events would otherwise race a total
                # that silently counted 0. #320 took the premise away — an
                # event whose quantities match no Cost Rate is now RECORDED
                # with its cost unresolved, and the unit total accumulates only
                # the known part, so the ceiling races a floor rather than a
                # zero. Refusing a start on a promise nothing keeps was the
                # remaining behaviour, and onboarding is not a wall: a tenant
                # part-way through declaring their cost rates starts limited
                # work like anyone else. The floor says so downstream (#328):
                # the unit counts what its total could not include and publishes
                # the count on every read of it, which is where the honesty
                # belongs — a start gate cannot tell a caller that a running
                # total is incomplete. The race is still under-firing rather
                # than over-firing: a unit is never killed for spend UBB cannot
                # demonstrate.
                from apps.platform.work.services import TaskService

                task = TaskService.create_task(
                    tenant=customer.tenant,
                    customer=customer,
                    parent=parent,
                    balance_snapshot_micros=balance,
                    provider_cost_limit_micros=provider_cost_limit_micros,
                    metadata=task_metadata or {},
                    external_task_id=external_task_id,
                    # Tier-2 (D4/I6): pin the resolved billing owner on the task.
                    billing_owner_id=owner.id,
                    # Design D7/D6: ONE column carries the declared kind of
                    # work at either altitude (#407), so the resolved key is
                    # written the same way whether or not there is a parent —
                    # and `parent` above is what says which altitude it is at.
                    task_type=resolved_key,
                    dimension_slots=slot_values,
                )
            result["task_id"] = str(task.id)
            result["parent_task_id"] = str(parent.id) if parent else None
            result["provider_cost_limit_micros"] = task.provider_cost_limit_micros
            result["task_type"] = task.task_type or None

        return result
