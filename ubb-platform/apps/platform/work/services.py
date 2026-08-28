import logging

from django.utils import timezone

from core.amount_status_pairs import CUSTOMER_PRICE, SUPPLIER_COST
from core.cost_totals import counts_as_unresolved
from core.vocabulary import (
    COSTING_STATUS_KNOWN,
    OUTCOME_REASON_VALUES,
    PRICING_STATUS_KNOWN,
    TASK_OUTCOME_CANCELLED,
    TASK_OUTCOME_DELIVERED,
    TASK_OUTCOME_FAILED,
    TASK_STATUS_ACTIVE,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_EXPIRED,
    TASK_STATUS_FAILED,
    TASK_STATUS_KILLED,
)
from apps.platform.grouping_fields.models import SLOTS
from apps.platform.work.models import TERMINAL_TASK_STATUSES, Task

logger = logging.getLogger(__name__)


# WHAT THE CALLER DECLARED, AND THE STATE THAT DECLARATION ENTERS (#409).
#
# ONE call, ONE mandatory field, ONE code path — and the winning transition is
# the exactly-once trigger a charge will later key on. Two endpoints was
# rejected as two of everything, and optional-with-a-delivered-default was
# rejected on the strongest rule available: THE FORGIVING PATH MUST NEVER BE
# THE MONEY-MOVING ONE. A dropped field, a stale example or an old client would
# otherwise bill a customer for work that failed.
#
# This map is also what makes a repeated close answerable. A close against a
# terminal unit is a REPLAY when the state it declares is the state the unit is
# already in, and a CONFLICT otherwise — so `killed` and `expired`, which no
# declaration maps onto, refuse every close by construction. That is the point
# rather than an edge case: a unit UBB killed on its ceiling that the tenant
# delivered anyway must not answer 200, because under a charge it would be
# silent revenue loss whose first symptom is a month-end number.
STATUS_FOR_OUTCOME = {
    TASK_OUTCOME_DELIVERED: TASK_STATUS_COMPLETED,
    TASK_OUTCOME_FAILED: TASK_STATUS_FAILED,
    TASK_OUTCOME_CANCELLED: TASK_STATUS_CANCELLED,
}

#: THE OUTCOMES A REASON MAY BE DECLARED BESIDE. Neither the code nor the
#: sentence is accepted on a declared delivery (spec §6): there is no *why it
#: did not deliver* for work that did, and accepting one would invite a caller
#: to explain a success — which is a field nothing can ever be grouped by.
OUTCOMES_ACCEPTING_A_REASON = frozenset({TASK_OUTCOME_FAILED,
                                         TASK_OUTCOME_CANCELLED})

#: ...AND THE ONES THAT REQUIRE IT. Only `failed`. A cancellation is usually
#: self-explanatory and the caller may say no more; a failure without a stated
#: cause is the row a dashboard cannot act on. `unspecified` is what keeps the
#: requirement cheap — the caller always has a valid answer to give.
OUTCOMES_REQUIRING_A_REASON = frozenset({TASK_OUTCOME_FAILED})


class DeclarationRefused(ValueError):
    """An ill-formed close declaration, with the field that spoiled it.

    A ValueError subclass rather than a `Problem`: this module is a PRODUCT and
    the error dialect belongs to the composition layer (ADR-001). The endpoint
    translates; what is decided here is the rule, which is the half that must
    not have two copies.
    """

    def __init__(self, field, detail):
        self.field = field
        super().__init__(detail)


class CloseDeclaration:
    """WHAT A CALLER SAYS WHEN IT CLOSES A UNIT OF WORK — the outcome, the
    reason for it, and the sentence beside that.

    ⚠ ONE OBJECT BECAUSE IT IS ONE STATEMENT, and the three parts are not
    independently meaningful: whether a reason is required, permitted or
    refused is a fact about the OUTCOME, so a caller passing them separately
    passes three things that can only be judged together. They travelled as
    three arguments through four layers before this existed, unbundled and
    rebundled at each, which is how one of the layers comes to disagree about
    the rule.

    It also gives the replay comparison somewhere honest to live: deciding
    whether a second close says the same thing is a question about a
    declaration, not about a task row.
    """

    __slots__ = ("outcome", "outcome_reason", "reason_detail")

    def __init__(self, outcome, outcome_reason="", reason_detail=""):
        self.outcome = outcome
        self.outcome_reason = outcome_reason or ""
        self.reason_detail = reason_detail or ""

    @classmethod
    def declared(cls, outcome, outcome_reason=None, reason_detail=None):
        """Build one from what arrived on the wire, or refuse it.

        ⚠ `None` AND `""` ARE DIFFERENT ON THE WAY IN and the same on the way
        out. Absent means *the caller said nothing*, which is what "required on
        `failed`" is about; once judged, both are stored as `""`, because a
        column has no third state and *nobody gave one* is what `""` means.
        """
        if outcome not in STATUS_FOR_OUTCOME:
            raise DeclarationRefused(
                "outcome",
                f"outcome must be one of {', '.join(sorted(STATUS_FOR_OUTCOME))}")

        if outcome not in OUTCOMES_ACCEPTING_A_REASON:
            if outcome_reason is not None or reason_detail is not None:
                raise DeclarationRefused(
                    "outcome_reason",
                    f"outcome_reason and reason_detail are not accepted when "
                    f"the outcome is {outcome}")
        elif outcome_reason is None:
            if outcome in OUTCOMES_REQUIRING_A_REASON:
                raise DeclarationRefused(
                    "outcome_reason",
                    f"outcome_reason is required when the outcome is {outcome}")
        elif outcome_reason not in OUTCOME_REASON_VALUES:
            # ⚠ AN UNRECOGNISED REASON IS REFUSED, AND THE ARGUMENT THAT
            # SOFTENS UBB'S OWN STOP REASONS DOES NOT TRANSFER. `reasons.py`
            # reconciles its own closed set with an open registry concept by
            # ruling that closed binds UBB's PRODUCERS while open binds
            # CONSUMERS — which holds only because a stop reason is
            # UBB-produced. This value arrives from outside, so the closed set
            # is a rule on what may come in (spec §6).
            raise DeclarationRefused(
                "outcome_reason",
                f"{outcome_reason!r} is not a recognised outcome_reason")

        # ⚠ AND THE SENTENCE IS NEVER VALIDATED AGAINST A VOCABULARY. It is the
        # cardinality guard that lets the code above stay a small closed set,
        # and checking it would defeat the only thing it is for.
        return cls(outcome, outcome_reason, reason_detail)

    def entered_status(self):
        """The state this declaration puts a unit of work into."""
        return STATUS_FOR_OUTCOME[self.outcome]

    def already_recorded_on(self, task):
        """Does ``task`` already hold exactly what this declaration says?

        True makes a second close a REPLAY; False makes it a CONFLICT, and
        `killed` and `expired` are conflicts by construction because no
        declaration enters either.

        ⚠ THE SENTENCE IS DELIBERATELY NOT COMPARED, and the code beside it is.
        Spec §5 refuses "any different declaration", and the outcome and its
        reason are both declared — but `reason_detail` is free text that is
        never validated and never grouped on, so a retry that re-worded a
        provider's message would be refused for a difference with no
        consequence anywhere. What is compared is what UBB would have to
        contradict itself to accept.
        """
        return (task.status == self.entered_status()
                and task.outcome_reason == self.outcome_reason)


#: WHY A START WAS REFUSED BY THE SHAPE OF THE WORK, in the words the start
#: gate's verdict vocabulary already publishes (`openapi/error-codes.json`).
#: Named rather than spelled at each raise so a caller — and a test — asserts
#: the SYMBOL: the words themselves belong to a vocabulary slice 6 rebuilds,
#: and a literal in twelve places is twelve edits when it does.
PARENT_NOT_ACTIVE = "parent_task_not_active"
SUBTASK_DEPTH_EXCEEDED = "subtask_depth_exceeded"

#: THE FACTS A UNIT OF WORK SNAPSHOTS AT ITS START AND CANNOT THEN CHANGE, as
#: this module names them. `StartDeclaration.conflicting_field_on` answers with
#: one of these and the composition layer says which request field the caller
#: must look at, because the two vocabularies are genuinely different: the
#: grouping bag's wire key is another slice's retired word, and `parent` here is
#: a row while `parent_task_id` out there is an identifier in a body.
#:
#: Named constants rather than literals so a test asserts the SYMBOL. A test
#: comparing against its own copy of the string passes whatever this module
#: decides to say, which is the half that decays silently.
PINNED_PARENT = "parent"
PINNED_TASK_TYPE = "task_type"
PINNED_COST_CEILING = "provider_cost_limit_micros"
PINNED_GROUPING_VALUES = "grouping_values"


class StartRefused(ValueError):
    """A start refused by the work it names, carrying the reason.

    A `ValueError` subclass for `DeclarationRefused`'s reason one class up:
    this module is a PRODUCT-side kernel and the error dialect belongs to the
    composition layer (ADR-001). What is decided here is the rule.
    """

    def __init__(self, reason, detail):
        self.reason = reason
        super().__init__(detail)


class StartDeclaration:
    """WHAT A CALLER SAYS WHEN IT REGISTERS A UNIT OF WORK — the key claiming
    the attempt, and the five facts the unit then snapshots.

    ⚠ ONE OBJECT FOR THE SAME REASON `CloseDeclaration` IS ONE: the parts are
    not independently meaningful. Deciding whether a repeated start is a retry
    or a contradiction is a question about the WHOLE declaration, and a caller
    passing the parts separately passes things that can only be judged
    together.

    **The key and the label are two fields doing two jobs.** The key identifies
    ONE ATTEMPT and is required and unique; `external_task_id` is the caller's
    free-text JOB LABEL, reusable across attempts. Promoting the label to the
    key was rejected: the label is the only place the relationship BETWEEN
    attempts can live, so making it the identity would force attempt 2 to be
    called something else and leave nothing tying the attempts together.
    """

    __slots__ = ("idempotency_key", "parent_task_id", "task_type",
                 "slot_values", "provider_cost_limit_micros",
                 "external_task_id", "metadata")

    def __init__(self, idempotency_key, *, parent_task_id=None, task_type="",
                 slot_values=None, provider_cost_limit_micros=None,
                 external_task_id="", metadata=None):
        self.idempotency_key = idempotency_key
        self.parent_task_id = parent_task_id
        self.task_type = task_type or ""
        self.slot_values = dict(slot_values or {})
        self.provider_cost_limit_micros = provider_cost_limit_micros
        self.external_task_id = external_task_id or ""
        self.metadata = dict(metadata or {})

    def conflicting_field_on(self, task):
        """The first PINNED field this declaration states differently from
        ``task``, or ``None`` when the two say the same thing.

        `None` makes a repeated start a REPLAY — the caller gets back the unit
        it already started. A name makes it a CONFLICT, and the name is the
        whole value of the refusal: *this key is taken* sends a caller looking
        through its own code, while *this key is taken and you asked for a
        different parent* is the sentence that ends the search.

        **THE PINNED FIELDS ARE THE ONES THE UNIT SNAPSHOTS AND CANNOT CHANGE.**
        A silent replay across a differing one would hand back a unit of work
        that is not the one the caller just described — and under a whole-job
        price a differing kind of work IS a differing price, so the tenant
        would be charged the render price for a transcode job while its own
        records said otherwise.

        ⚠ THE COMPARISON IS AGAINST THE DECLARATION, NEVER AGAINST A
        RE-RESOLUTION, and that is what makes the retry work FOREVER rather
        than until the tenant next edits their configuration. Re-deriving the
        ceiling or re-validating the kind of work here would let a tenant
        lowering a default, or retiring a kind of work, turn every in-flight
        retry into a refusal — the one case a permanently-claimed key exists to
        answer. Every field below is compared as the caller stated it.

        ⚠ THE CUSTOMER IS PINNED AND CANNOT APPEAR HERE, which is not an
        omission. The claim is scoped `(tenant, customer, key)`, so the same
        key under a different customer finds no claim at all and starts a
        second, legitimate unit of work. That is the uniqueness rule doing the
        pinning; there is no row to contradict.

        ⚠ THE NAMES RETURNED ARE THIS MODULE'S, NOT THE WIRE'S, and the
        composition layer translates — the same split `DeclarationRefused`
        takes one class up, where the rule is the product's and the dialect is
        the API layer's. It is load-bearing here for a second reason: the wire
        key for the grouping bag is retired vocabulary under a spread ceiling
        another slice owns, so spelling it in this module would put the word in
        one more file and fail the sweep for a debt this commit does not own.
        """
        if self.parent_task_id != task.parent_id:
            return PINNED_PARENT
        if self.task_type != task.task_type:
            return PINNED_TASK_TYPE
        # ⚠ COMPARED ONLY WHERE THE CALLER NAMED ONE, and the asymmetry is the
        # field's own meaning rather than a softening. A caller-supplied
        # ceiling is a request for a LOWER one than the kind of work already
        # carries — never a higher one — so naming it states a ceiling and
        # omitting it states only *whatever this kind of work says*, which is
        # not a claim that can contradict anything. Where one IS named, it is
        # the resolved ceiling by construction: the resolution returns a
        # supplied value unchanged or refuses the request outright.
        if (self.provider_cost_limit_micros is not None
                and self.provider_cost_limit_micros
                != task.provider_cost_limit_micros):
            return PINNED_COST_CEILING
        if self.slot_values != {slot: getattr(task, slot) for slot in SLOTS
                                if getattr(task, slot)}:
            return PINNED_GROUPING_VALUES
        return None


class TaskService:

    @staticmethod
    def claimed_by(tenant, customer, idempotency_key):
        """The unit of work this key already claims for this customer, or None.

        A pure read, and it is deliberately the FIRST thing the start gate
        does. Everything else a start runs — the wallet checks, the grouping
        values it would record, the concurrency slot it would count against —
        either spends something or reads something that moves, so a retry that
        reached them would be paying twice for an answer that is already
        written down. Answering the repeat from the claim itself is what makes
        *a replay creates nothing* a property of the gate rather than a
        by-product of a constraint firing later.
        """
        return Task.objects.filter(
            tenant=tenant, customer=customer,
            idempotency_key=idempotency_key).first()

    @staticmethod
    def parent_for(tenant, customer, parent_task_id):
        """Resolve and LOCK the parent a contained start names, or refuse.

        Returns None when nothing is named — a top-level start, which is the
        common case and has no parent to check.

        Locking here is what makes contained work safe to register: the row is
        held for the rest of the caller's transaction, so a cascade that
        withdraws or kills this parent cannot interleave and leave a step born
        under an already-terminal unit. It takes the PARENT-first lock order
        `Task.parent` states, which is the order rollup and both cascades take.

        The refusals are legitimate in the way the start gate's refusals always
        are: they refuse work that has not happened yet, never a usage report.
        A missing or foreign parent reads as not-active — a unit that does not
        exist here is not an active one — and the depth refusal WINS over
        status for a row that does exist, because the structural mistake is the
        actionable one.
        """
        if parent_task_id is None:
            return None
        parent = Task.objects.select_for_update().filter(
            id=parent_task_id, tenant=tenant, customer=customer).first()
        if parent is None:
            raise StartRefused(
                PARENT_NOT_ACTIVE,
                "the parent named is not an active unit of work")
        if parent.parent_id is not None:
            raise StartRefused(
                SUBTASK_DEPTH_EXCEEDED,
                "contained work cannot contain further work "
                "(one containment level at launch)")
        if parent.status != TASK_STATUS_ACTIVE:
            raise StartRefused(
                PARENT_NOT_ACTIVE,
                f"the parent named is {parent.status}, not active")
        return parent

    @staticmethod
    def create_task(tenant, customer, balance_snapshot_micros,
                    provider_cost_limit_micros=None,
                    metadata=None, external_task_id="", billing_owner_id=None,
                    parent=None, task_type="", dimension_slots=None,
                    idempotency_key=None):
        """Create a Task, snapshotting limit config and wallet balance.
        Passing ``parent`` registers a SUBTASK under it (#38) — a Task row
        with the self-FK set, one containment level at launch.

        Limits are passed explicitly by the caller — the start gate at
        ``api/v1/task_endpoints.py`` — which owns the ceiling ladder, the
        money-shaped admission and the parent active/depth refusals; the depth
        guard here is defense in depth against internal misuse. Tier-2 (D4):
        billing_owner_id is PINNED here (resolve_billing_owner) so the
        concurrency slot + reapers never re-resolve a re-parented owner. Must
        be called inside @transaction.atomic.

        ``idempotency_key`` is the caller's claim on this attempt (#410), and
        it is pass-through like everything else here: this seam writes the key
        it is handed and the DATABASE decides whether the claim stands. It
        defaults to None because the reapers, the cascades and every fixture
        that stands a unit of work up directly are not callers making a claim,
        and a synthesised key would be a fabricated declaration.

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
            idempotency_key=idempotency_key,
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
    def _flip(task_id, status, *, cascade_to, reason="", declaration=None,
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

        ``declaration`` is the `CloseDeclaration` the CALLER made, written in
        the same UPDATE as the state it explains so the two can never come
        apart (#409). It is a separate argument from ``reason`` because they
        are separate concepts with separate owners: ``reason`` is UBB's own
        stop reason and lands in `metadata`, a declaration is the caller's
        closed-set outcome reason and its free-text sentence, and they land in
        columns. Only a close passes one — nothing UBB decides on its own may
        write a field that means *the tenant said so*.

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
        if declaration is not None:
            task.outcome_reason = declaration.outcome_reason
            task.reason_detail = declaration.reason_detail
            update_fields += ["outcome_reason", "reason_detail"]
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
        and `reason_code: silence_window` for an expiry cascade. Both still
        arrive with the containment ticket that owns the cascade itself — the
        column `parent_closed` will land in EXISTS as of #409, so what is left
        owing is the cascade's own decision to write it, which is a behaviour
        change to this function rather than a value set to take ownership of.
        The STATE is what is written here today, and a withdrawn piece of
        contained work is already distinguishable from a delivered one without
        the reason.
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
    def close_task(task_id, declaration):
        """THE TENANT DECLARED HOW THIS ENDED, and a close is the only writer
        of any of the three states it can enter (I1, spec §2 and §5). Nothing
        else writes `completed` — which is what makes the state safe for a
        charge to key on, and is exactly the property the model could not offer
        while a sweeper wrote it too.

        ``declaration`` is REQUIRED and this method has no default,
        deliberately: a default here would put the forgiving path back under
        the money-moving one, one layer below where the API refuses it. Build
        it with `CloseDeclaration.declared`, which is where an ill-formed one
        is refused — so by the time it reaches here the outcome is known good
        and the reason rules have already been applied.

        ⚠ THE CASCADE WITHDRAWS, IT DOES NOT DELIVER, AND IT DOES NOT INHERIT.
        Closing a PARENT flips its still-active contained work to `cancelled`
        in the same transaction (#38) — cleanup is still one call — WHATEVER
        the parent's own outcome was. The tenant declared how the whole unit
        ended and declared nothing at all about each contained piece: writing
        `completed` there would be UBB declaring a delivery on the tenant's
        behalf, and inheriting `failed` would record the pieces that worked as
        failures because the last one did. Already-terminal contained work
        keeps its own outcome; closing contained work closes it alone.

        Must be called inside @transaction.atomic.
        """
        return TaskService._flip(
            task_id, declaration.entered_status(),
            cascade_to=TASK_STATUS_CANCELLED, declaration=declaration)
