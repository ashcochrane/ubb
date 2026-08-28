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
        "no type-level opinion", and `resolve_start_policy` below applies the
        RiskConfig rung. Start gates call THAT one — this is the top of the
        ladder rather than the whole of it.

        ⚠ IT ADMITS THE GROUPING VALUES, WHICH IS A WRITE. A caller that only
        needs to know what a declaration binds to — a repeated start comparing
        itself against the unit it may be replaying — must use
        `DimensionService.resolve`, or a start that is about to be refused
        permanently burns a key's cardinality for work that never began.
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
    def resolve_start_policy(tenant, *, task_type, dimensions,
                             requested_limit_micros, is_subtask):
        """``resolve_type_policy`` above plus the REST OF THE CEILING LADDER,
        so a start gate resolves a unit's COGS ceiling in one call.

        Precedence, unchanged in every particular (design D7, #37, #38): the
        caller's request (only if at or below the declared default) -> the
        declared kind of work's default -> the tenant's RiskConfig default for
        this altitude -> uncapped, and no signal ever fires.

        ⚠ THE LADDER IS ONE THING AND IT IS HERE BECAUSE IT WAS TWO. Its top
        two rungs were resolved in the method above and its third was applied
        by the caller, so the answer to *what ceiling does this unit get* was
        assembled in two places and only ever read as a whole. The ceiling is
        universal — a tenant who never enables billing still declares kinds of
        work and still gets their ceilings — so the composition layer asks this
        for every start, whatever the tenant's posture, and asks the
        money-shaped questions below separately.
        """
        key, slot_values, limit = RiskService.resolve_type_policy(
            tenant, task_type=task_type, dimensions=dimensions,
            requested_limit_micros=requested_limit_micros,
            is_subtask=is_subtask)
        if limit is None:
            config = RiskService._config(tenant)
            if config is not None:
                limit = (config.default_subtask_provider_cost_limit_micros
                         if is_subtask
                         else config.default_task_provider_cost_limit_micros)
        return key, slot_values, limit

    @staticmethod
    def _config(tenant):
        try:
            return tenant.risk_config
        except RiskConfig.DoesNotExist:
            return None

    @staticmethod
    def concurrency_verdict(customer, balance_micros=None):
        """The ONE control only a call that registers work can breach.

        ``check`` below answers the advisory question — *is this customer in a
        state where UBB would let work proceed* — and every verdict it gives is
        a verdict for a start too. This is the remainder: a per-owner cap on
        work ALREADY RUNNING, which has nothing to say to a caller that is not
        about to add to it.

        ⚠ IT IS ITS OWN METHOD RATHER THAN A FLAG ON `check`, because the two
        questions have different answers and both are published. Folding the
        cap in would make the advisory endpoint start reporting a verdict it
        has never reported, on a surface slice 6 owns and this commit is not
        rebuilding. Keeping them apart is also what lets the start gate run
        them in the order it has always run them, with the parent's own
        liveness checked between the two.

        Tier-2 P5 (D11/I6): the slot count is simply how much work is ACTIVE
        for the billing owner — accurate and leak-free, with no Redis slot to
        leak, and the reaper frees capacity by terminating stale work. A pooled
        business shares one cap because every seat's work pins it as billing
        owner. The bounded over-admit on the read-then-create race is accepted.
        Contained work holds a slot like anything else — a contained unit is
        still parallel work.
        """
        from apps.platform.tenants.flags import enforcing
        from apps.billing.accounts import resolve_billing_owner
        config = RiskService._config(customer.tenant)
        # > 0 (not truthiness): 0/NULL = no concurrency cap, and a negative
        # mis-config can never block every start (mirrors the rpm > 0 guard).
        if (enforcing(customer.tenant) and config
                and config.max_concurrent_requests
                and config.max_concurrent_requests > 0):
            from apps.platform.work.models import Task
            owner = resolve_billing_owner(customer)
            running = Task.objects.filter(
                billing_owner_id=owner.id, status="active").count()
            if running >= config.max_concurrent_requests:
                return {"allowed": False, "reason": "concurrency_limit",
                        "balance_micros": balance_micros}
        return {"allowed": True, "reason": None,
                "balance_micros": balance_micros}

    @staticmethod
    def check(customer, parent_task_id=None):
        """The advisory answer: may work proceed for this customer?

        Read-only in the sense that matters — it authors no unit of work. It
        used to, behind a flag, and registering a unit of work is now its own
        call at the root (`POST /api/v1/tasks`, #410): a money-shaped
        admission check and the registration of a unit of work were one call
        answering two questions, and only one of them was ever about money.

        ``parent_task_id`` is still read, and only for the soft floor: past the
        wind-down line NEW top-level work is refused while a contained start
        under a running parent passes, so the answer differs by altitude even
        though nothing is created here.
        """
        from apps.billing.accounts import resolve_billing_owner
        owner = resolve_billing_owner(customer)
        # Status: gate if the seat OR its billing-owner (business) is suspended/closed
        for who in ([customer] if owner.id == customer.id else [customer, owner]):
            if who.status == "suspended":
                return {"allowed": False, "reason": "insufficient_funds", "balance_micros": None}
            if who.status == "closed":
                return {"allowed": False, "reason": "account_closed", "balance_micros": None}
        # Tier-2 P6: honor the synchronous customer-wide stop flag at the
        # start-gate (enforcing only — the flag cannot exist for an off
        # tenant) so a flag-stopped owner's NEW tasks are blocked even before
        # the durable suspend lands, and for postpaid owner-aggregate stops.
        from apps.platform.tenants.flags import enforcing
        if enforcing(customer.tenant):
            from apps.billing.gating.services.live_counter import LiveCounter
            if LiveCounter.read(owner.id, customer.tenant)["stop"]:
                return {"allowed": False, "reason": "customer_stopped",
                        "balance_micros": None}
        config = RiskService._config(customer.tenant)
        # Fixed-window rate limiting (per-seat; degrades gracefully if Redis is down)
        if config and config.max_requests_per_minute and config.max_requests_per_minute > 0:
            try:
                cache_key = f"ratelimit:{customer.id}:rpm"
                current_count = cache.get(cache_key, 0)
                if current_count >= config.max_requests_per_minute:
                    return {"allowed": False, "reason": "rate_limit_exceeded", "balance_micros": None}
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
            return {"allowed": False, "reason": "insufficient_funds", "balance_micros": balance}

        # Soft floor (#40, spec §F): past the resolved wind-down line, NEW
        # TOP-LEVEL task starts are refused — running tasks may complete, so
        # a subtask start under a parent passes (a contained child of running
        # work is running work completing; the parent's own liveness is
        # validated separately, by `TaskService.parent_for`, under that
        # parent's own lock). enforcing-only, like every state change; the
        # hard-floor refusal above wins below both lines. Wallet-based, so
        # postpaid has no soft floor.
        if (parent_task_id is None and enforcing(customer.tenant)
                and owner.tenant.billing_mode != "postpaid"):
            from apps.billing.queries import get_customer_soft_min_balance
            from apps.billing.gating.services.stop_signal_service import SOFT_FLOOR_REACHED
            soft = get_customer_soft_min_balance(owner.id, owner.tenant_id)
            if past_floor(balance, soft):
                return {"allowed": False, "reason": SOFT_FLOOR_REACHED,
                        "balance_micros": balance}

        # Budget cap: checked per-seat (customer, not owner)
        from apps.billing.gating.services.budget_service import BudgetService
        budget = BudgetService.check(customer)
        if not budget["allowed"]:
            return {"allowed": False, "reason": budget["reason"],
                    "balance_micros": balance}

        # THE PARENT THE SOFT FLOOR ABOVE READS IS CHECKED ELSEWHERE NOW.
        # Whether that named parent is a live, top-level unit is a
        # structural question about the work rather than a money-shaped
        # one, so `TaskService.parent_for` asks it, under the parent's own
        # lock, in the same transaction as the write it guards.
        return {"allowed": True, "reason": None, "balance_micros": balance}
