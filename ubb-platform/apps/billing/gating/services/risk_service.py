from typing import NamedTuple

from core.vocabulary import (
    AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED,
    AFFORDABILITY_REASON_CUSTOMER_STOPPED,
    AFFORDABILITY_REASON_INSUFFICIENT_FUNDS,
    AFFORDABILITY_REASON_SOFT_FLOOR_REACHED,
    PRICING_MODE_EVENT_PRICED, TASK_TYPE_KIND_SUBTASK, TASK_TYPE_KIND_TASK)

from core.crossing import past_floor
from apps.platform.work import admission, reasons


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

        ⚠ IT CONTAINS NO THROTTLE, AND ASKING IT CONSUMES NOTHING (#462,
        slice 6 §6). The per-minute bound on new work ran here until #462,
        incrementing its window on every call — so the advisory question
        spent the allowance it was asking about, and a tenant without a
        wallet, for whom the composition layer never asks this, had no bound
        at all. Admission control is the kernel's now (`work/admission.py`),
        asked by the composition layer for every start before this verdict,
        and this answers the money-shaped verdict only: standing, the stop
        in force, the hard floor, the soft floor at the altitude
        ``parent_task_id`` names, and the pool. The standing check is kept
        here as well, for the advisory read — it is the one place a
        suspended customer's refusal can name which line opened it.

        ``parent_task_id`` is still read, and only for the soft floor: past the
        wind-down line NEW top-level work is refused while a contained start
        under a running parent passes, so the answer differs by altitude even
        though nothing is created here.
        """
        from apps.billing.accounts import resolve_billing_owner
        owner = resolve_billing_owner(customer)
        # THE STANDING IS THE KERNEL'S WALK, WORDED HERE (#462): the seat,
        # then the business funding a pooled seat, refused in the word of the
        # line holding it — which this verdict is the one place to name.
        standing, who = admission.standing_refusal(customer)
        if standing is not None:
            return _verdict(RiskService.standing_word(standing, who), None, None)
        # Tier-2 P6: honor the synchronous customer-wide stop flag at the
        # start-gate (enforcing only — the flag cannot exist for an off
        # tenant) so a flag-stopped owner's NEW tasks are blocked even before
        # the durable suspend lands, and for owner-aggregate pool stops.
        from apps.platform.tenants.flags import enforcing
        if enforcing(customer.tenant):
            from apps.billing.gating.services.live_counter import LiveCounter
            if LiveCounter.read(owner.id, customer.tenant)["stop"]:
                return _verdict(AFFORDABILITY_REASON_CUSTOMER_STOPPED, None, None)

        # Affordability check: read wallet from billing owner (business for pooled seat, else self)
        from apps.billing.wallets.models import Wallet
        try:
            balance = Wallet.objects.get(customer=owner).balance_micros
        except Wallet.DoesNotExist:
            balance = 0

        # AFFORDABILITY IS THE BALANCE LESS OPEN RESERVATIONS (#461, slice 6
        # §5, #139 §4.1), tested against the tenant's own floors and never a
        # new threshold. A prepaid start of a kind of work sold at one agreed
        # price reserves that price (`reserve_agreed_price` below); every
        # start on the wallet lane is then judged on what is left after the
        # work already admitted — so three starts cannot each read the same
        # balance and all pass. Postpaid reserves nothing, so its term is
        # zero without a read.
        on_the_wallet_lane = owner.tenant.billing_mode != "postpaid"
        reserved = 0
        floors = NO_FLOORS
        if on_the_wallet_lane:
            from apps.billing.wallets.reservations import open_reservations_micros
            reserved = open_reservations_micros(owner.id)
            floors = _floors(owner.id, customer.tenant, parent_task_id)
        available = balance - reserved

        # The hard floor, then the soft floor at its own altitude — the one
        # walk `reserve_agreed_price` makes again with the price included.
        # Wallet-based, so postpaid has neither, and reports neither.
        refusal = _floor_refusal(available, floors)
        if refusal is not None:
            return _verdict(refusal, balance, available, floors)

        # Customer spend pool, the SEAT level (slice 6 §4): the seat's own
        # counter against the seat's pool. The owner level refuses through
        # the owner's suspension and flag above.
        from apps.billing.gating.services.customer_spend_pool_service import CustomerSpendPoolService
        pool = CustomerSpendPoolService.check(customer)
        if not pool["allowed"]:
            return _verdict(pool["reason"], balance, available, floors)

        # THE PARENT THE SOFT FLOOR ABOVE READS IS CHECKED ELSEWHERE NOW.
        # Whether that named parent is a live, top-level unit is a
        # structural question about the work rather than a money-shaped
        # one, so `TaskService.parent_for` asks it, under the parent's own
        # lock, in the same transaction as the write it guards.
        return _verdict(None, balance, available, floors)

    @staticmethod
    def standing_word(reason, who):
        """The money verdict's word for a customer the kernel's admission
        check found not in standing (#462): a suspension in the word of the
        line holding it (#459 — the pool's where the pool alone holds, else
        the wallet's, read off the OPEN ledger lines of ``who``, the seat or
        the business funding it), and a closure in the registry's own word.
        Asked by ``check`` above and by the start's composition on the
        kernel's refusal, so a suspended customer of a tenant with a wallet
        is told the same thing by both."""
        if reason == AFFORDABILITY_REASON_CUSTOMER_STOPPED:
            return _suspension_refusal(who)
        return reason

    @staticmethod
    def reserve_agreed_price(customer, task, *, parent_task_id=None):
        """The reservation half of the money-shaped verdict (#461, slice 6
        §5, #139 §4.1): reserve the price ``task`` pinned against the owner's
        wallet, or refuse the start because doing so would leave the available
        amount past a floor.

        Called by the start, in the start's own transaction, AFTER the unit's
        row is written and the price is pinned on it — the reservation is
        keyed on the unit and the price is the unit's — and after ``check``
        has already answered everything else money-shaped. What this adds is
        the one question ``check`` cannot ask before the price is known: not
        *is the customer past a floor now* but *would admitting THIS start
        put it there*. The same floors, the same orientation, the same words
        (`insufficient_funds`; `soft_floor_reached` for a top-level start
        under the switch, the altitude ``check`` reads the soft floor at) —
        never a new threshold.

        ⚠ UNDER THE OWNER'S BILLING LOCK, which is what makes the answer exact
        under concurrency: two starts racing for the last affordable slot
        serialize here, the second reads the first's committed row, and
        exactly as many succeed as the balance affords. The lock is held to
        the start's commit and taken after the parent's row lock (the start
        resolves the parent first), which is the one order every lane holding
        both takes.

        Reserves nothing, and answers allowed, wherever there is nothing to
        reserve: a postpaid tenant (no wallet to encumber — the same fork
        ``check`` makes) and a unit with no pinned price (event-priced work,
        contained work). A tenant that does not bill through UBB never
        reaches here: the composition layer conditions the whole money-shaped
        half on the product, as it does for ``check``.

        The owner is the one the unit's start already stamped
        (``task.billing_owner_id``, resolved by the same rule ``check`` uses)
        rather than a second resolution of it. The billing lock creates the
        owner's wallet lazily where none exists — a billing tenant's customer
        who has never been credited — which is the row every credit and
        drawdown path would create on its first use anyway: a reservation
        against a wallet is what makes the wallet exist. ``parent_task_id``
        reaches the soft floor's altitude check exactly as ``check``'s does;
        today only a top-level start carries a price, so only a top-level
        start is refused here on the wind-down line.
        """
        from apps.billing.locking import lock_for_billing
        from apps.billing.wallets import reservations

        tenant = customer.tenant
        price = task.agreed_price_micros
        if tenant.billing_mode == "postpaid" or price is None:
            return _verdict(None, None, None)

        owner_id = task.billing_owner_id
        wallet, _owner_row = lock_for_billing(owner_id)
        balance = wallet.balance_micros
        available = balance - reservations.open_reservations_micros(owner_id)
        floors = _floors(owner_id, tenant, parent_task_id)
        refusal = _floor_refusal(available - price, floors)
        if refusal is not None:
            return _verdict(refusal, balance, available, floors)

        reservations.reserve(task=task, owner_id=owner_id, tenant=tenant,
                             amount_micros=price)
        return _verdict(None, balance, available, floors)


class Floors(NamedTuple):
    """Wallet policy's two lines, RESOLVED for one owner at one altitude —
    the figures a money-shaped verdict tested the available amount against,
    reported beside the verdict so a caller reading `insufficient_funds` or
    `soft_floor_reached` also reads the line it was refused on (#463, slice
    6 §13). Both carry the orientation the billing profile and the tenant
    configuration already publish them in: the value is the allowed
    overdraft, so the line sits at `-value`.
    """

    #: The hard floor: customer override -> tenant default -> 0. `None` only
    #: where no floor applies at all (postpaid, or an answer made before a
    #: wallet was read).
    min_balance_micros: int | None
    #: The soft floor AT THE ALTITUDE THE QUESTION NAMED. `None` where no
    #: wind-down line applies to this start: contained work under a running
    #: parent, a tenant not enforcing, or no soft floor configured at either
    #: level — the same three conditions under which `_floor_refusal` never
    #: says `soft_floor_reached`, so the figure and the refusal cannot
    #: disagree about whether the line was tested.
    soft_min_balance_micros: int | None


#: The floors where no wallet lane applies: a postpaid owner, or a verdict
#: made before any wallet was read.
NO_FLOORS = Floors(None, None)


def _floors(owner_id, tenant, parent_task_id):
    """Resolve Wallet policy's two lines for ``owner_id`` at the altitude
    ``parent_task_id`` names — the one read `check` and
    `reserve_agreed_price` both make, so the figures they report are the
    figures they compared against.

    The soft floor (#40, spec §F) applies to NEW TOP-LEVEL starts only —
    a contained child of running work is running work completing — and
    only under the switch, like every state change; where it does not
    apply it is resolved as `None` rather than as a figure that was never
    tested.
    """
    from apps.billing.queries import (
        get_customer_min_balance, get_customer_soft_min_balance)
    from apps.platform.tenants.flags import enforcing

    hard = get_customer_min_balance(owner_id, tenant.id)
    soft = None
    if parent_task_id is None and enforcing(tenant):
        soft = get_customer_soft_min_balance(owner_id, tenant.id)
    return Floors(hard, soft)


def _verdict(reason, balance_micros, available_micros, floors=NO_FLOORS):
    """The money-shaped answer's one shape: allowed iff there is no reason;
    the balance and the balance less open reservations beside it, both
    ``None`` where the answer was made before a wallet was read; and the
    two resolved floors the available amount was tested against, `None`
    on the same terms and wherever no floor applies (`Floors`)."""
    return {"allowed": reason is None, "reason": reason,
            "balance_micros": balance_micros,
            "available_micros": available_micros,
            "min_balance_micros": floors.min_balance_micros,
            "soft_min_balance_micros": floors.soft_min_balance_micros}


def _floor_refusal(available_micros, floors):
    """The refusal word Wallet policy's floors give ``available_micros``, or
    ``None`` where both admit it — the walk ``check`` and
    ``reserve_agreed_price`` share, so the two cannot disagree about a line.

    The hard floor first, always. Then the soft floor, wherever `_floors`
    resolved one for this altitude: past the wind-down line NEW TOP-LEVEL
    starts are refused while a contained start under a running parent
    passes (the parent's own liveness is validated separately, by
    `TaskService.parent_for`, under that parent's own lock), and the hard
    floor's refusal wins below both lines. `NO_FLOORS` — a postpaid owner —
    admits everything: the wallet lane's lines do not exist for it.
    """
    if floors.min_balance_micros is None:
        return None
    if past_floor(available_micros, floors.min_balance_micros):
        return AFFORDABILITY_REASON_INSUFFICIENT_FUNDS
    if past_floor(available_micros, floors.soft_min_balance_micros):
        return AFFORDABILITY_REASON_SOFT_FLOOR_REACHED
    return None
