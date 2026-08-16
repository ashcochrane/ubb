import logging
from collections import namedtuple
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from uuid import UUID

from django.db import transaction, IntegrityError
from django.utils import timezone

from core.time_windows import month_bounds
from apps.metering.usage.grouping import grouping_fields_for
from apps.metering.usage.models import (
    BackfillDirtyPeriod, Posting, PostingMeasurement)
from apps.platform.events.outbox import write_event
from apps.platform.events.schemas import UsageRecorded
from apps.platform.grouping_fields.models import SLOTS

logger = logging.getLogger(__name__)

# THE RETIRING BAG'S VALIDATION DIED WITH THE BAG (#273), AND THE SURVIVOR DOES
# NOT INHERIT IT. It enforced FOUR rules and each is answered separately here,
# because "it validated the field we deleted" is a reason to look at them, not a
# reason to drop them unexamined.
#
#   1. A lowercase-snake KEY PATTERN. Retired on the merits: that pattern exists
#      so keys make stable chart labels — a *grouping* rule wearing a validation
#      hat. The survivor is never groupable, and enforcing it would be UBB
#      dictating the shape of identifiers the tenant authored, on the very
#      commit that rules UBB never rewords them.
#   2. VALUES MUST BE STRINGS. Cannot be carried: the surviving bag has always
#      held arbitrary JSON and nesting is a real, intended use of it (a request
#      envelope, a client block). Imposing it would break callers of a field
#      that never had the rule.
#   3. AT MOST 50 KEYS and 4. VALUES UNDER 256 CHARS. Size guards, not
#      vocabulary — but they are also rules the surviving bag never had, and
#      adding them here would narrow a published field this ticket was not
#      asked to narrow. Left off deliberately, and recorded as the open
#      question they are rather than quietly dropped.
#
# THE CONSEQUENCE, STATED IN THE DIRECTION IT ACTUALLY RUNS. A caller whose keys
# the retired bag refused with a 422 now gets a 200 — that much is the #272
# precedent. But the removal also WIDENS what can reach the three grouping
# surfaces slice 7 owns: they used to read a bag validated flat `str -> str` and
# now read the same arbitrary JSON everything else in this bag may hold, so a
# key-driven chart or invoice line label can be handed a serialised object
# rather than a short string. Nothing is mis-metered and no money moves — the
# bag is filtered and read, never priced — but this is a widening on the very
# surfaces this ticket must not widen, and it is slice 7's to close when it
# moves that capability onto the declared grouping contract.
# `tests/test_the_second_open_bag_folds.py` pins both halves.

# Tolerated clock skew for caller-supplied effective_at in the future.
_FUTURE_SKEW = timedelta(minutes=5)


def _tenant_currency(tenant):
    """CUR-1: the tenant's single event currency, normalized lowercase — the
    ONE rule both the endpoint adapter's mismatch check and the recording
    input's stamp share."""
    return (tenant.default_currency or "usd").lower()


class EffectiveAtError(ValueError):
    """A caller-supplied effective_at was rejected. ``code`` is the typed
    machine-readable reason surfaced as the API error code (422)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def validate_effective_at(tenant, owner_id, effective_at, now):
    """Validate a caller-supplied effective_at at the record_usage choke point.

    Raises EffectiveAtError with code:
    - effective_at_naive      — no timezone info;
    - effective_at_in_future  — more than _FUTURE_SKEW ahead of now;
    - effective_at_too_old    — older than tenant.backfill_window_days
                                (0 = no backfill: any past timestamp rejected);
    - billing_period_closed   — the billing OWNER's postpaid usage invoice for
                                the EFFECTIVE month is FROZEN (status
                                pushing/pushed/skipped/failed_permanent, a
                                non-empty push_phase, a stripe_invoice_id
                                pointer, OR a frozen line_snapshot — the
                                snapshot check is load-bearing: lines freeze
                                at first claim, before any Stripe call). A
                                genuinely-fresh ``pending`` row (empty
                                snapshot) is safely re-aggregable and does
                                NOT block.
    """
    if effective_at.tzinfo is None or effective_at.utcoffset() is None:
        raise EffectiveAtError(
            "effective_at_naive",
            "effective_at must be timezone-aware (e.g. 2026-06-01T12:00:00Z)")
    if effective_at > now + _FUTURE_SKEW:
        raise EffectiveAtError(
            "effective_at_in_future",
            f"effective_at is more than {int(_FUTURE_SKEW.total_seconds() // 60)} "
            "minutes in the future")
    window_days = tenant.backfill_window_days
    if effective_at < now - timedelta(days=window_days):
        raise EffectiveAtError(
            "effective_at_too_old",
            f"effective_at is older than this tenant's backfill window "
            f"({window_days} days)")
    # Closed-period guard: keyed on the billing OWNER (a pooled seat's backfill
    # must respect the business's invoice). Cross-product read goes through the
    # billing read contract (apps.billing.queries) — sanctioned channel.
    from apps.billing.queries import is_usage_period_closed
    period_start, _ = month_bounds(effective_at)
    if is_usage_period_closed(owner_id, period_start):
        raise EffectiveAtError(
            "billing_period_closed",
            f"the billing period starting {period_start.isoformat()} has already "
            "been invoiced; backfills into it are rejected")


def _inherit_dimensions(task_id, dimension_slots):
    """Resolve the twelve INHERITABLE selector values for one event (design D6).

    Twelve, not fourteen: `provider` and `event_type` are the caller's own on
    every event and are never inherited from the unit of work, so they are not
    resolved here. The other two reserved axes are, and so are the ten slots.

    Precedence per slot: the event's own value, then the leaf unit's, then its
    parent's, then "". `task_type` always comes from the ROOT of the chain and
    `subtask_type` from the leaf when it has a parent — so a subtask's events
    carry both without the caller repeating either.

    One query for the leaf and one for its parent; containment is a single
    level (tasks/models.py:34-38), so this never recurses.
    """
    out = {"task_type": "", "subtask_type": ""}
    out.update({s: (dimension_slots or {}).get(s, "") for s in SLOTS})
    if task_id is None:
        return out

    from apps.platform.work.models import Task
    cols = ("id", "parent_id", "task_type", "subtask_type") + SLOTS
    leaf = Task.objects.filter(id=task_id).values(*cols).first()
    if leaf is None:
        return out

    if leaf["parent_id"] is None:
        out["task_type"] = leaf["task_type"]
        chain = (leaf,)
    else:
        out["subtask_type"] = leaf["subtask_type"]
        root = Task.objects.filter(id=leaf["parent_id"]).values(*cols).first()
        out["task_type"] = (root or {}).get("task_type", "")
        chain = (leaf, root) if root else (leaf,)

    for slot in SLOTS:
        if out[slot]:
            continue  # the event's own value wins
        for unit in chain:
            if unit and unit.get(slot):
                out[slot] = unit[slot]
                break
    return out


_UNRESOLVED = object()  # sentinel: _result should look the parent up itself


def _result(event, *, task_total_billed=None, task_total_provider=None,
            task_total_unresolved=None,
            stop=False, stop_reason=None, stop_scope=None,
            suspended=False, new_balance_micros=None,
            parent_task_id=_UNRESOLVED):
    """Build the record_usage response.

    One-rule (#37): every recorded event answers success; the stop
    instruction rides these fields. The named unit's BOTH running totals
    travel, denominationally explicit; ``parent_task_id`` names the unit's
    parent when the unit is a subtask (#38) — the happy path passes it from
    the accumulated row, replay paths leave it to the fallback lookup here
    (parent is immutable, so a replay can never read it stale).

    Tier-2 (D5/I4): the customer-wide spend-stop verdict travels on EVERY
    return path of record_usage — the happy path AND both idempotent-replay
    returns — so a replayed event for an already-stopped owner never reports
    "all clear".
    """
    if parent_task_id is _UNRESOLVED:
        parent_task_id = None
        if event.task_id:
            from apps.platform.work.models import Task
            parent_task_id = Task.objects.filter(
                id=event.task_id).values_list("parent_id", flat=True).first()
    return {
        "event_id": str(event.id),
        "provider_cost_micros": event.provider_cost_micros,
        # Read off the row rather than assumed here, so an idempotent replay
        # answers what the original recording concluded (#317). The cause and
        # the caller's claim ride the same rule (#323): all three are columns,
        # and a replay that re-derived any of them could answer differently
        # from the recording it is replaying.
        "costing_status": event.costing_status,
        "unresolved_reason": event.unresolved_reason,
        "claimed_provider_cost_micros": event.claimed_provider_cost_micros,
        "billed_cost_micros": event.billed_cost_micros,
        "new_balance_micros": new_balance_micros, "suspended": suspended,
        "task_id": str(event.task_id) if event.task_id else None,
        "parent_task_id": str(parent_task_id) if parent_task_id else None,
        "task_total_billed_cost_micros": task_total_billed,
        "task_total_provider_cost_micros": task_total_provider,
        # The unit total above is a FLOOR wherever this is non-zero (#328) — a
        # caller watching its own spend against a COGS limit is watching a
        # lower bound, and the limit has therefore not been shown to be safe.
        "task_total_unresolved_event_count": task_total_unresolved,
        "stop": stop, "stop_reason": stop_reason, "stop_scope": stop_scope,
        # The itemized past-limit array (#41, spec §H) — read from the event
        # row, so idempotent replays return the ORIGINAL context unchanged.
        "stop_context": event.stop_context,
        "measurements": event.measurements,
        "pricing_provenance": event.pricing_provenance,
        # The grouping values under the tenant's OWN keys (#277). #276 left a
        # published-name/column mismatch here and ticket 20 resolved it by the
        # per-slot properties going away rather than by either side being
        # re-spelled: the second and third slots used to be published and the
        # rest were not, which is a pair no reader could have predicted.
        #
        # Inherited values are in here too: task- and subtask-scoped values are
        # set at the start gate and never travel with the event (D6), so this is
        # where a caller sees them WITHOUT a second call. The detail response
        # serves the same object off the same row.
        "grouping_fields": grouping_fields_for(event),
    }


def _tag_stop_context(event, **builder_kwargs):
    """Stop-context tagging (#41, spec §H): run the ONE builder and persist a
    non-empty array onto the just-created event. The write is a queryset update
    — the model save() guard keeps the event immutable to everything else —
    inside the recording transaction, so the row is never visible untagged
    ("set at record time")."""
    from apps.metering.usage.services.stop_context import build_stop_context
    ctx = build_stop_context(**builder_kwargs)
    if ctx is not None:
        Posting.objects.filter(id=event.id).update(stop_context=ctx)
        event.stop_context = ctx


def _replay_stop(customer, tenant):
    """Customer-wide stop verdict for the idempotent-replay return paths.
    Skips the owner resolve + Redis read entirely when enforcement is off, so
    the common replay path stays fast for un-enrolled tenants."""
    from apps.platform.tenants.flags import enforcing
    if not enforcing(tenant):
        return {}
    from apps.billing.queries import read_live_stop
    return read_live_stop(customer.resolve_billing_owner().id, tenant)


@dataclass(frozen=True)
class RecordingInput:
    """The recording core's typed input (#112): already-validated,
    already-normalized facts — currency stamped from the tenant, declared
    slot values resolved, billing owner resolved. Internal to the metering service;
    it never appears in the API surface. Build it via ``gather``, never by
    hand — the normalization rules live there once."""

    # tenant / customer / owner_row are platform-kernel ORM rows, annotated
    # loosely to keep this module's import surface flat.
    tenant: object
    customer: object
    request_id: str
    idempotency_key: str
    metadata: dict
    event_type: str
    provider: str
    currency: str
    measurements: dict
    task_type: str
    subtask_type: str
    grouping_field_1: str
    grouping_field_2: str
    grouping_field_3: str
    grouping_field_4: str
    grouping_field_5: str
    grouping_field_6: str
    grouping_field_7: str
    grouping_field_8: str
    grouping_field_9: str
    grouping_field_10: str
    task_id: UUID | None
    billing_owner_id: UUID
    # The resolved billing-owner ROW for stop-context tagging (status already
    # in hand — no extra query).
    owner_row: object
    effective_at: datetime | None
    caller_provider_cost: int | None
    #: What the caller BELIEVES the call cost — recorded as stated and never
    #: rated. It sits beside `caller_provider_cost` and is never read with it:
    #: the pricing spine below is never handed this value at all, which is what
    #: keeps "never COGS" a property of the code rather than a convention.
    claimed_provider_cost: int | None
    caller_billed: int | None
    now: datetime

    @classmethod
    def gather(cls, *, tenant, customer, request_id, idempotency_key,
               metadata, event_type, provider, measurements,
               task_id, caller_provider_cost, claimed_provider_cost,
               caller_billed, effective_at, billing_owner_id, owner_row,
               now, dimension_slots=None):
        """The normalization the recording path runs: tenant-currency stamp,
        declared-grouping-field slot fill, and the ``or ""``/``or {}`` defaults
        the posting create relies on. Validation does NOT live here — the
        endpoint adapter validates before building.

        ``dimension_slots`` is an ALREADY-ADMITTED {slot: value} map (Task 9:
        DimensionService.admit ran in the caller — gather() never admits).
        The open bag is labelling only (#37) and is never consulted for
        grouped values — the historical "product"/"service"/"agent"
        label-lifting is retired.

        Grouping fields are DECLARED and INHERITED (design D1/D6) — there is no
        label-fallback inference and no legacy ``product_id`` wire field: the
        write contract's only path onto a slot is a declared grouping field
        bound to it (DimensionService.admit), same as any other.
        ``_inherit_dimensions`` resolves the fourteen selector columns per
        slot: this event's own value wins, else the leaf task's, else its
        parent's, else ""."""
        slots = dict(dimension_slots or {})
        dims = _inherit_dimensions(task_id, slots)
        return cls(
            tenant=tenant, customer=customer,
            request_id=request_id or "", idempotency_key=idempotency_key,
            metadata=metadata or {},
            event_type=event_type or "", provider=provider or "",
            # CUR-1: every event is denominated in the tenant's single
            # currency, stored normalized lowercase. The sync adapter has
            # already rejected any mismatching caller currency.
            currency=_tenant_currency(tenant),
            measurements=measurements or {},
            **dims,
            task_id=task_id, billing_owner_id=billing_owner_id,
            owner_row=owner_row, effective_at=effective_at,
            caller_provider_cost=caller_provider_cost,
            claimed_provider_cost=claimed_provider_cost,
            caller_billed=caller_billed, now=now)


# What the recording core hands back: the created event row, the accumulate
# primitive's outputs (both None for an unattributed event), and the
# live-debit verdict dict.
RecordingOutcome = namedtuple("RecordingOutcome", "event task verdicts live")


class RecordingConflict(IntegrityError):
    """The recording savepoint (price → create → accumulate) hit an
    IntegrityError — the core's idempotency boundary (#112). The typed
    re-raise lets ``record_usage`` react to THIS boundary alone: an
    IntegrityError from a post-savepoint stage (live-debit ledger, outbox)
    stays a plain IntegrityError and propagates as the hard failure it is
    (500 + full rollback — the event was NOT durably recorded without its
    emission), instead of being misread as an idempotent replay of its own
    just-created row."""


def _execute_kills(kills, *, tenant_id, customer_id):
    """One-rule (#37): run the recording core's kill plan post-commit — the
    idempotent active->killed flip + task.limit_exceeded /
    subtask.limit_exceeded on the winning transition (kill_and_announce). The
    event is ALREADY recorded and billed — the kill is a signal, never a
    wall, so it runs in its own transaction after the recording committed. A
    subtask's own crossing kills it ALONE; a parent crossing kills the parent
    and cascades downward inside kill_task (#38).

    Per-kill try/except + loud log: kill_and_announce already never raises,
    but an on_commit callback that raised would abort every later callback in
    the chain, so the belt-and-braces guard lives HERE too (#112, D2)."""
    from apps.platform.work.services import TaskService
    for target_id, reason in kills:
        try:
            TaskService.kill_and_announce(
                target_id, reason, tenant_id=tenant_id, customer_id=customer_id)
        except Exception:
            logger.exception("usage.kill_failed", extra={"data": {
                "task_id": str(target_id), "reason": reason,
                "tenant_id": str(tenant_id)}})


class UsageService:
    @staticmethod
    def _record_core(inp):
        """The recording body (#112): price → create → accumulate inside a
        savepoint, then live-debit → stop-context tag → backfill-dirty marker
        → UsageRecorded emission → kill registration. ``record_usage`` is a
        thin input adapter over this core.

        Must run inside the caller's transaction (write_event asserts it). The
        savepoint around price/create/accumulate is the idempotency boundary:
        its IntegrityError propagates as RecordingConflict, with everything
        after it unentered, and ``record_usage`` answers it with the replay
        result.

        Kill execution (#112): the core computes reasons.kill_plan inside the
        recording transaction and registers execution on its own
        transaction.on_commit — forgetting the old endpoint-side pop
        protocol is now structurally impossible. Registered AFTER write_event so
        the callback order stays outbox-dispatch → kills, exactly as it was
        when the endpoint executed kills after the commit."""
        from apps.metering.pricing.services.pricing_service import PricingService
        tenant, customer = inp.tenant, inp.customer
        task = None
        verdicts = None
        try:
            with transaction.atomic():
                # as_of=effective_at prices on the card versions valid at the
                # EFFECTIVE time (None → the pricer's own now()).
                selectors = {"provider": inp.provider, "event_type": inp.event_type,
                             "task_type": inp.task_type,
                             "subtask_type": inp.subtask_type,
                             **{slot: getattr(inp, slot) for slot in SLOTS}}
                costing = PricingService.price(
                    tenant=tenant, customer=customer, selectors=selectors,
                    measurements=inp.measurements,
                    currency=inp.currency,
                    caller_provider_cost=inp.caller_provider_cost,
                    caller_billed=inp.caller_billed,
                    as_of=inp.effective_at)
                # THE STATUS IS THE SPINE'S ANSWER, CARRIED — NOT RE-DERIVED
                # (#320). Nothing here re-reads the amount to decide whether it
                # is known: a second definition of "unresolved" one layer up is
                # exactly how the two come to disagree.
                provider_cost_micros = costing.provider_cost_micros
                billed_cost_micros = costing.billed_cost_micros
                provenance = costing.pricing_receipt
                create_kwargs = {}
                if inp.effective_at is not None:
                    create_kwargs["effective_at"] = inp.effective_at
                event = Posting.objects.create(
                    tenant=tenant, customer=customer, request_id=inp.request_id,
                    idempotency_key=inp.idempotency_key, metadata=inp.metadata,
                    event_type=inp.event_type, provider=inp.provider,
                    provider_cost_micros=provider_cost_micros,
                    costing_status=costing.costing_status,
                    unresolved_reason=costing.unresolved_reason,
                    # WRITTEN AT INSERT AND ONLY AT INSERT. The column is
                    # declared FROZEN and #318's trigger enforces it: what a
                    # caller said they believed at the time is a record of the
                    # call, and a claim that could be edited afterwards would
                    # be an opinion rather than evidence. It passes the spine
                    # by — nothing above rated it, and nothing below sums it.
                    claimed_provider_cost_micros=inp.claimed_provider_cost,
                    billed_cost_micros=billed_cost_micros,
                    currency=inp.currency,
                    pricing_provenance=provenance,
                    task_id=inp.task_id,
                    billing_owner_id=inp.billing_owner_id,
                    task_type=inp.task_type, subtask_type=inp.subtask_type,
                    **{slot: getattr(inp, slot) for slot in SLOTS},
                    **create_kwargs)
                # The measurement record (#270), written in the SAME
                # transaction as its posting — the child's whole-record rule
                # says "insert once, with the parent", and the savepoint above
                # is what makes that true of a failure too.
                #
                # This is the metered recording path, so every posting it
                # records has one, empty bag or not. Absence is reserved for the
                # posting kind that never had measurements, and manufacturing an
                # empty child here would spend that meaning on a bag the caller
                # simply left out. `prunable_at` stays NULL: no document states
                # the horizon and nothing in this repository sets it.
                PostingMeasurement.objects.create(
                    posting=event, measurements=inp.measurements or {},
                    recorded_at=event.created_at)
                if inp.task_id is not None:
                    # One-rule: the ONE accumulate primitive — always records
                    # both totals (the tipping event and everything after a
                    # kill land, bill, and count) and returns crossing
                    # verdicts instead of raising. The event create above and
                    # this accumulate share the savepoint, so totals and
                    # events can never diverge.
                    from apps.platform.work.services import TaskService
                    task, verdicts = TaskService.accumulate_cost(
                        inp.task_id, billed_cost_micros=billed_cost_micros,
                        provider_cost_micros=provider_cost_micros,
                        # The spine's answer, carried rather than re-derived
                        # (#328): the unit counts what it could not add, and
                        # only the status tells an unresolved cost apart from
                        # one the Event Type declares does not exist.
                        costing_status=costing.costing_status,
                        tenant_id=tenant.id, customer_id=customer.id)
        except IntegrityError as exc:
            raise RecordingConflict(str(exc)) from exc
        # Tier-2 (P2/WS1): maintain the synchronous live counter on the SAME
        # billing owner the async drawdown will debit. Reached only once the
        # event has committed to the savepoint (the IntegrityError replay race
        # propagates above, so a duplicate never double-decrements). No-op when
        # enforcement_mode is off. Routed through the sanctioned billing
        # read/port contract (apps.billing.queries) — metering must not import
        # a billing internal directly (product-boundary ADR-001).
        from apps.billing.queries import record_live_usage_debit
        live = record_live_usage_debit(
            inp.billing_owner_id, tenant, billed_cost_micros,
            effective_at=inp.effective_at, now=inp.now) or {}
        # Stop-context tagging (#41): runs AFTER the live debit so a fresh
        # crossing (stop_episode_opened) marks THIS event as the episode's
        # tipping event; still inside the recording transaction.
        _tag_stop_context(
            event, task=task, verdicts=verdicts, now=inp.now,
            owner=inp.owner_row, tenant=tenant,
            opened_episode_seq=live.get("stop_episode_opened"))
        if inp.effective_at is not None:
            eff_month_start = month_bounds(inp.effective_at)[0]
            if eff_month_start < month_bounds(inp.now)[0]:
                # Backfill into a PRIOR month: mark the period dirty so the
                # hourly resnapshot task refreshes its margin snapshot. Same
                # transaction as the event; savepoint-IntegrityError-swallow
                # (billing/handlers.py pattern) absorbs the unique-marker
                # race.
                try:
                    with transaction.atomic():
                        BackfillDirtyPeriod.objects.create(
                            tenant=tenant, customer=customer,
                            period_start=eff_month_start)
                except IntegrityError:
                    pass  # marker already pending for this (tenant, customer, period)
        write_event(UsageRecorded(
            tenant_id=str(tenant.id), customer_id=str(customer.id),
            event_id=str(event.id),
            cost_micros=billed_cost_micros,
            provider_cost_micros=provider_cost_micros,
            # Read off the row rather than re-derived from the amount (#328).
            # A subscriber accumulating this payload has to tell a cost UBB has
            # not learned from one that does not exist, and the amount alone
            # cannot: both arrive as null.
            costing_status=event.costing_status,
            billed_cost_micros=billed_cost_micros,
            event_type=inp.event_type, provider=inp.provider,
            task_id=str(inp.task_id) if inp.task_id else None,
            billing_owner_id=str(inp.billing_owner_id),
            # Normalized to UTC: the instance attribute keeps the caller's
            # original offset, but consumers bucket by UTC calendar month.
            effective_at=event.effective_at.astimezone(dt_timezone.utc).isoformat()))
        if verdicts is not None:
            from apps.platform.work import reasons
            kills = reasons.kill_plan(task.id, task.parent_id, verdicts)
            if kills:
                transaction.on_commit(
                    lambda: _execute_kills(kills, tenant_id=tenant.id,
                                           customer_id=customer.id))
        return RecordingOutcome(event, task, verdicts, live)

    @staticmethod
    @transaction.atomic
    def record_usage(tenant, customer, request_id, idempotency_key, *,
                     provider_cost_micros=None,
                     claimed_provider_cost_micros=None,
                     billed_cost_micros=None,
                     provider="", event_type="", currency=None,
                     metadata=None, task_id=None, measurements=None,
                     effective_at=None, dimension_slots=None):
        """The recording path (#112): validation + replay + owner resolve,
        then the recording core. The keyword surface is the input adapter every
        service-level call site and both recording endpoints already speak; it
        lost the nameless inline quantity in #272, lost the second open bag in
        #273, and gained the caller's own claimed cost in #324.

        ``dimension_slots`` (Task 9) is an already-admitted {slot: value} map
        — the caller (endpoint / record_sync_item) runs DimensionService.admit
        BEFORE calling this, so a DimensionError is the whole-request/whole-
        item rejection and never reaches here.

        ``provider_cost_micros`` is admitted the same way (#324): WHETHER a
        caller may state the supplier's own cost turns on the Event Type's
        declaration, and `metering_endpoints.admit_supplier_cost` answers it
        for both routes before this runs. Whichever figure arrives here is
        costed — that separation is what lets the batch route refuse one item
        without disturbing the others, and it is why nothing below re-asks."""
        # select_related on the measurement child (#270): a replay's response
        # carries the ORIGINAL quantities, which the posting now reads through
        # the child — and the replay path is the hot one, so it pays for that
        # read here rather than a second query per retry.
        existing = Posting.objects.select_related("measurement").filter(
            tenant=tenant, customer=customer, idempotency_key=idempotency_key).first()
        if existing:
            # Replay wins BEFORE effective_at validation: a whole-batch retry
            # must return the original event even if the window has since aged
            # past the timestamp or the period closed.
            return _result(existing, **_replay_stop(customer, tenant))
        now = timezone.now()
        # Billing owner hoisted above pricing: the closed-period guard and the
        # pinned billing_owner_id both key on the same resolver result. The
        # ROW is kept, not just the id — stop-context tagging reads its
        # status without a second resolve.
        owner = customer.resolve_billing_owner()
        owner_id = owner.id
        if effective_at is not None:
            validate_effective_at(tenant, owner_id, effective_at, now)
        # CUR-1 choke point: every event is denominated in the tenant's single
        # currency. A caller-supplied currency must MATCH it (case-insensitive)
        # or the event is rejected — no FX, no mixed-currency data. The
        # normalized stamp itself is gather()'s job.
        tenant_currency = _tenant_currency(tenant)
        if currency:
            currency = str(currency).strip().lower()
            if currency != tenant_currency:
                raise ValueError(
                    f"currency mismatch: event currency {currency!r} does not "
                    f"match tenant currency {tenant_currency!r} (per-tenant "
                    "single currency; multi-currency/FX is not supported)")
        inp = RecordingInput.gather(
            tenant=tenant, customer=customer, request_id=request_id,
            idempotency_key=idempotency_key, metadata=metadata,
            event_type=event_type, provider=provider,
            measurements=measurements,
            task_id=task_id,
            caller_provider_cost=provider_cost_micros,
            claimed_provider_cost=claimed_provider_cost_micros,
            caller_billed=billed_cost_micros, effective_at=effective_at,
            billing_owner_id=owner_id, owner_row=owner, now=now,
            dimension_slots=dimension_slots)
        try:
            outcome = UsageService._record_core(inp)
        except RecordingConflict as exc:
            # ONLY the savepoint's typed conflict — a post-savepoint
            # IntegrityError propagates as the hard failure it is (it cannot
            # be a replay: our own row exists), exactly as on main.
            try:
                existing = Posting.objects.select_related("measurement").get(
                    tenant=tenant, customer=customer, idempotency_key=idempotency_key)
            except Posting.DoesNotExist:
                # Not the idempotency duplicate — some other insert inside the
                # savepoint failed (counter/task machinery). Surface the original
                # IntegrityError attributably instead of masking it as a replay
                # (or as an unexplained DoesNotExist).
                raise exc
            return _result(existing, **_replay_stop(customer, tenant))
        task, live = outcome.task, outcome.live
        # Stop-verdict fields: a task/subtask-scoped verdict wins the scalar
        # slot over the customer-wide verdict (which still surfaces on the
        # next ack and via stop.fired); among unit verdicts the WIDEST
        # tripped scope wins — reasons.stop_fields owns that priority. The
        # itemized multi-limit story is the past-limit ticket's stop_context
        # array.
        stop = live.get("stop", False)
        stop_reason = live.get("stop_reason")
        stop_scope = live.get("stop_scope")
        if outcome.verdicts is not None:
            from apps.platform.work import reasons
            unit_reason, unit_scope = reasons.stop_fields(
                outcome.verdicts, is_subtask=task.parent_id is not None)
            if unit_reason is not None:
                stop, stop_reason, stop_scope = True, unit_reason, unit_scope
        return _result(outcome.event,
                       task_total_billed=task.total_billed_cost_micros if task else None,
                       task_total_provider=task.total_provider_cost_micros if task else None,
                       task_total_unresolved=task.unresolved_event_count if task else None,
                       parent_task_id=task.parent_id if task else None,
                       stop=stop, stop_reason=stop_reason, stop_scope=stop_scope)
