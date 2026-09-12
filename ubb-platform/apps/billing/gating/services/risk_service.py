from typing import NamedTuple

from django.core.cache import cache

from core.vocabulary import (
    AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED,
    AFFORDABILITY_REASON_INSUFFICIENT_FUNDS,
    PRICING_MODE_EVENT_PRICED, TASK_TYPE_KIND_SUBTASK, TASK_TYPE_KIND_TASK)

from core.crossing import past_floor
from apps.billing.gating.models import RiskConfig
from apps.platform.work import reasons


def _suspension_refusal(customer):
    """The refusal word for a suspended customer (slice 6 §4, #459): a
    customer the pool alone is holding is refused in the pool's own word;
    every other suspension — the wallet floor's, an administrative one, or
    both lines at once, where the money-shaped refusal has always won below
    both — in the word the gate has always used. Read off the OPEN ledger
    lines rather than the suspension's own word, because the suspension
    records the stop that OPENED it and that stop may since have lifted
    while the other still holds (#458's two independent episodes)."""
    from apps.billing.gating.services.stop_signal_service import StopSignalService
    holding = {row["reason"] for row in StopSignalService.open_stop_lines(customer.id)}
    if holding == {reasons.CUSTOMER_SPEND_POOL}:
        return AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED
    return AFFORDABILITY_REASON_INSUFFICIENT_FUNDS


class StartPolicy(NamedTuple):
    """EVERYTHING A START PINS OFF THE DECLARED KIND OF WORK, as one answer.

    A NamedTuple rather than a bare tuple because the four are not
    interchangeable and `[0]` / `[3]` at the call site says nothing about which
    is which — two of them are strings, so a mis-ordered unpack would put a
    kind of work where a regime belongs and be caught by nothing.
    `work/queries.ExpiryWindows` is the house precedent and makes the argument
    at length.

    It is still a tuple, which is what keeps this a plain-data answer rather
    than an object the caller has to know how to drive.
    """

    #: The declared kind of work, validated and unretired — "" for a tenant who
    #: declared no vocabulary at all.
    task_type: str
    #: The grouping values ADMITTED for this start, already bound to slots.
    grouping_slots: dict
    #: The COGS ceiling, after the whole ladder. `None` means no ceiling
    #: applies to this unit — its kind declared `uncapped`, or it has no
    #: declared kind and the tenant declares no default at its altitude — and
    #: the unit's assessment then says `not_applicable` on every surface.
    task_cogs_ceiling_micros: int | None
    #: HOW THIS KIND OF WORK IS SOLD (#414, #415), which a start snapshots onto
    #: the unit of work and, where it is one agreed price, resolves an amount
    #: for. `event_priced` for a tenant who declared no vocabulary: an untyped
    #: unit of work has no declaration to have said otherwise, and that is what
    #: every unit of work in the system meant before the column existed.
    pricing_mode: str


class RiskService:
    @staticmethod
    def resolve_start_policy(tenant, *, task_type, dimensions,
                             requested_ceiling_micros, is_subtask):
        """Validate the declared kind of work + dimensions and resolve the
        ceiling — the WHOLE ladder, in one call, for every start.

        ``task_type`` is the caller's declared kind of work at EITHER altitude
        (#407): a unit of work declares its kind once, and whether it has a
        parent is what says which altitude it is at. ``is_subtask`` is that
        parent link, which is why the declaration this looks up is chosen by it
        and not by which of two fields the caller filled in.

        TWO LADDERS, AND WHICH ONE RUNS IS DECIDED BY WHETHER A KIND WAS
        DECLARED (#453, slice 6 §2, #150 §8):

            a declared kind      caller's request (lower only) -> the declaration
            no declared kind     caller's request (lower only) -> the tenant's
                                 default for this altitude -> no ceiling applies

        A declared kind answers for itself — its figure, or `uncapped` — and
        the tenant's default is never consulted for it: a declaration that
        states nothing does not exist, because the database refuses it. The
        tenant's rung is for work that has no declaration to answer, and where
        the tenant declares none either, no ceiling applies and the unit's
        assessment says `not_applicable` rather than staying silent (#150
        §8.2). A caller may request LOWER than whichever rung answers, never
        higher (#150 §8.3): the kind of work is declared by the platform team
        and the start call is made by agent code that may be generated or
        injected, and the ceiling is protection from your own agent. Where no
        rung answers, a request is a ceiling nobody else set, and it stands.

        ⚠ IT ADMITS THE GROUPING VALUES, WHICH IS A WRITE. A caller that only
        needs to know what a declaration binds to — a repeated start comparing
        itself against the unit it may be replaying — must use
        `DimensionService.resolve`, or a start that is about to be refused
        permanently burns a key's cardinality for work that never began.

        The ceiling is universal — a tenant who never enables billing still
        declares kinds of work and still gets their ceilings — so the
        composition layer asks this for every start, whatever the tenant's
        posture, and asks the money-shaped questions below separately.
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

        # THE RUNG A REQUEST IS HELD AGAINST. A declaration answers for itself
        # (its figure, or none by `uncapped`); undeclared work is answered by
        # the tenant's default for its altitude, read off the tenant row the
        # kernel owns (#141 §6.2) — never off billing's risk row, which is
        # exactly the row a tenant without billing does not have.
        if policy:
            authority = None if policy["uncapped"] else policy["task_cogs_ceiling_micros"]
            rung = f"the {kind} type ceiling"
        else:
            authority = (tenant.default_subtask_cogs_ceiling_micros if is_subtask
                         else tenant.default_task_cogs_ceiling_micros)
            rung = f"the tenant's default ceiling for undeclared {kind} work"
        if requested_ceiling_micros is not None:
            if authority is not None and requested_ceiling_micros > authority:
                raise ValueError(
                    f"task_cogs_ceiling_micros {requested_ceiling_micros} exceeds "
                    f"{rung} {authority}")
            ceiling = requested_ceiling_micros
        else:
            ceiling = authority
        # HOW THIS KIND OF WORK IS SOLD, READ OFF THE SAME DECLARATION THAT
        # SUPPLIED THE CEILING (#415). A tenant with no declared vocabulary
        # gets `event_priced` — not because nobody said, but because an untyped
        # unit of work has no declaration that could have said otherwise, and
        # per-event is what every unit of work in this system meant before the
        # column existed. It is the same default the column itself carries, for
        # the same reason.
        regime = policy["pricing_mode"] if policy else PRICING_MODE_EVENT_PRICED
        return StartPolicy(key, slot_values, ceiling, regime)

    @staticmethod
    def _config(tenant):
        try:
            return tenant.risk_config
        except RiskConfig.DoesNotExist:
            return None

    @staticmethod
    def check(customer, parent_task_id=None):
        """The advisory answer: may work proceed for this customer?

        Read-only in the sense that matters — it authors no unit of work. It
        used to, behind a flag, and registering a unit of work is now its own
        call at the root (`POST /api/v1/tasks`, #410): a money-shaped
        admission check and the registration of a unit of work were one call
        answering two questions, and only one of them was ever about money.

        Every verdict this gives is a verdict for a start too, and since #455
        it is the WHOLE money-shaped answer: the per-owner cap on work already
        running, which used to be the one control only a start could breach,
        is deleted (#150 §12.5) — it bounded a count of outstanding operations
        and converted to no amount of money.

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
                return {"allowed": False, "reason": _suspension_refusal(who),
                        "balance_micros": None}
            if who.status == "closed":
                return {"allowed": False, "reason": "account_closed", "balance_micros": None}
        # Tier-2 P6: honor the synchronous customer-wide stop flag at the
        # start-gate (enforcing only — the flag cannot exist for an off
        # tenant) so a flag-stopped owner's NEW tasks are blocked even before
        # the durable suspend lands, and for owner-aggregate pool stops.
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

        # Customer spend pool, the SEAT level (slice 6 §4): the seat's own
        # counter against the seat's pool. The owner level refuses through
        # the owner's suspension and flag above.
        from apps.billing.gating.services.customer_spend_pool_service import CustomerSpendPoolService
        pool = CustomerSpendPoolService.check(customer)
        if not pool["allowed"]:
            return {"allowed": False, "reason": pool["reason"],
                    "balance_micros": balance}

        # THE PARENT THE SOFT FLOOR ABOVE READS IS CHECKED ELSEWHERE NOW.
        # Whether that named parent is a live, top-level unit is a
        # structural question about the work rather than a money-shaped
        # one, so `TaskService.parent_for` asks it, under the parent's own
        # lock, in the same transaction as the write it guards.
        return {"allowed": True, "reason": None, "balance_micros": balance}
