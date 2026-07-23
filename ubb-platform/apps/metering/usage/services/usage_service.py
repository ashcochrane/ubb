import logging
import re
from collections import namedtuple
from dataclasses import dataclass
from datetime import timedelta, timezone as dt_timezone

from django.db import transaction, IntegrityError
from django.utils import timezone

from core.time_windows import month_bounds
from apps.metering.usage.models import BackfillDirtyPeriod, RawIngestEvent, UsageEvent
from apps.platform.events.outbox import write_event
from apps.platform.events.schemas import UsageRecorded

logger = logging.getLogger(__name__)

# Min 2 chars, max 64 chars, starts with letter, lowercase alphanumeric + underscores
TAG_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]{1,63}$')

# Tolerated clock skew for caller-supplied effective_at in the future.
_FUTURE_SKEW = timedelta(minutes=5)


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


def validate_tags(tags):
    """Validate tags dict. Raises ValueError on invalid input."""
    if tags is None:
        return
    if not isinstance(tags, dict):
        raise ValueError("tags must be a dict")
    if len(tags) > 50:
        raise ValueError("tags cannot have more than 50 keys")
    for key, value in tags.items():
        if not TAG_KEY_PATTERN.match(key):
            raise ValueError(
                f"tags key '{key}' must be lowercase alphanumeric + underscores, "
                "start with a letter, 2-64 chars"
            )
        if not isinstance(value, str):
            raise ValueError(f"tags value for '{key}' must be a string")
        if len(value) > 256:
            raise ValueError(f"tags value for '{key}' exceeds 256 chars")


_UNRESOLVED = object()  # sentinel: _result should look the parent up itself


def _result(event, *, task_total_billed=None, task_total_provider=None,
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
            from apps.platform.tasks.models import Task
            parent_task_id = Task.objects.filter(
                id=event.task_id).values_list("parent_id", flat=True).first()
    return {
        "event_id": str(event.id),
        "provider_cost_micros": event.provider_cost_micros,
        "billed_cost_micros": event.billed_cost_micros,
        "units": event.units,
        "new_balance_micros": new_balance_micros, "suspended": suspended,
        "task_id": str(event.task_id) if event.task_id else None,
        "parent_task_id": str(parent_task_id) if parent_task_id else None,
        "task_total_billed_cost_micros": task_total_billed,
        "task_total_provider_cost_micros": task_total_provider,
        "stop": stop, "stop_reason": stop_reason, "stop_scope": stop_scope,
        # The itemized past-limit array (#41, spec §H) — read from the event
        # row, so idempotent replays return the ORIGINAL context unchanged.
        "stop_context": event.stop_context,
        "usage_metrics": event.usage_metrics,
        "pricing_provenance": event.pricing_provenance,
        "service_id": event.service_id,
        "agent_id": event.agent_id,
    }


def _tag_stop_context(event, **builder_kwargs):
    """Stop-context tagging (#41, spec §H), shared by record and settle: run
    the ONE builder and persist a non-empty array onto the just-created
    event. The write is a queryset update — the model save() guard keeps the
    event immutable to everything else — inside the caller's recording
    transaction, so the row is never visible untagged ("set at record/settle
    time")."""
    from apps.metering.usage.services.stop_context import build_stop_context
    ctx = build_stop_context(**builder_kwargs)
    if ctx is not None:
        UsageEvent.objects.filter(id=event.id).update(stop_context=ctx)
        event.stop_context = ctx


def _parse_effective_at(payload):
    """Parse the ISO-8601 ``effective_at`` string a RawIngestEvent's payload
    carries (written by ``item.model_dump(mode="json")`` at accept time) back
    into a timezone-aware datetime, or None when absent. Uses
    ``django.utils.dateparse.parse_datetime`` — the same sanctioned parser
    outbox-payload consumers use elsewhere (apps/billing/handlers.py,
    apps/subscriptions/handlers.py) for this exact ISO-string-from-JSON shape."""
    raw = payload.get("effective_at")
    if not raw:
        return None
    from django.utils.dateparse import parse_datetime
    return parse_datetime(raw)


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
    already-normalized facts — currency stamped from the tenant, reserved
    tags extracted, billing owner resolved by the lane's adapter. Internal to
    the metering service; it never appears in the API surface. Build it via
    ``gather``, never by hand — the normalization rules live there once."""

    tenant: object
    customer: object
    request_id: str
    idempotency_key: str
    metadata: dict
    event_type: str
    provider: str
    currency: str
    usage_metrics: dict
    tags: dict | None
    product_id: str
    service_id: str
    agent_id: str
    task_id: object
    billing_owner_id: object
    # The resolved billing-owner ROW for stop-context tagging (status already
    # in hand — no extra query), or None when the lane skipped the fetch
    # (settle, enforcement off: no durable owner state can exist).
    owner_row: object
    effective_at: object
    units: object
    caller_provider_cost: object
    caller_billed: object
    now: object
    # Lane declaration: the sync lane maintains the live counter at record
    # time; the settle lane converges it via its hold true-up instead.
    debit_live_counter: bool

    @classmethod
    def gather(cls, *, tenant, customer, request_id, idempotency_key,
               metadata, event_type, provider, usage_metrics, tags,
               product_id, task_id, units, caller_provider_cost,
               caller_billed, effective_at, billing_owner_id, owner_row,
               now, debit_live_counter):
        """The shared normalization both lanes run: tenant-currency stamp,
        reserved-tag extraction (service/agent + the product fallback), and
        the ``or ""``/``or {}`` defaults the 14-field create relies on.
        Validation does NOT live here — the sync adapter validates before
        building; settle never rejects, by construction."""
        _tags = tags or {}
        return cls(
            tenant=tenant, customer=customer,
            request_id=request_id or "", idempotency_key=idempotency_key,
            metadata=metadata or {},
            event_type=event_type or "", provider=provider or "",
            # CUR-1: every event is denominated in the tenant's single
            # currency, stored normalized lowercase. The sync adapter has
            # already rejected any mismatching caller currency.
            currency=(tenant.default_currency or "usd").lower(),
            usage_metrics=usage_metrics or {}, tags=tags,
            # Tags are analytics-only labels (#37): the task_id request field
            # is the ONLY unit attribution — no tag-fallback inference.
            # product is the one reserved-tag fallback both lanes share.
            product_id=product_id or _tags.get("product", "") or "",
            service_id=_tags.get("service", ""),
            agent_id=_tags.get("agent", ""),
            task_id=task_id, billing_owner_id=billing_owner_id,
            owner_row=owner_row, effective_at=effective_at, units=units,
            caller_provider_cost=caller_provider_cost,
            caller_billed=caller_billed,
            now=now, debit_live_counter=debit_live_counter)


# What the recording core hands back to its lane: the created event row, the
# accumulate primitive's outputs (both None for an unattributed event), and
# the live-debit verdict dict ({} for the settle lane).
RecordingOutcome = namedtuple("RecordingOutcome", "event task verdicts live")


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
    from apps.platform.tasks.services import TaskService
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
        """The ONE recording body under both lanes (#112): price → create →
        accumulate inside a savepoint, then live-debit (sync lane only) →
        stop-context tag → backfill-dirty marker → UsageRecorded emission →
        kill registration. record_usage and settle_raw are thin input
        adapters over this core, so the lanes structurally cannot drift.

        Must run inside the calling lane's transaction (write_event asserts
        it). The savepoint around price/create/accumulate is the idempotency
        boundary: its IntegrityError PROPAGATES, with everything after it
        unentered — each lane keeps its own reaction (sync: replay result;
        settle: duplicate-flip under a fresh lock).

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
        with transaction.atomic():
            # as_of=effective_at prices on the card versions valid at the
            # EFFECTIVE time (None → the pricer's own now()).
            provider_cost_micros, billed_cost_micros, provenance = PricingService.price(
                tenant=tenant, customer=customer, event_type=inp.event_type,
                provider=inp.provider, usage_metrics=inp.usage_metrics,
                tags=inp.tags, currency=inp.currency,
                caller_provider_cost=inp.caller_provider_cost,
                caller_billed=inp.caller_billed, units=inp.units,
                as_of=inp.effective_at)
            create_kwargs = {}
            if inp.effective_at is not None:
                create_kwargs["effective_at"] = inp.effective_at
            event = UsageEvent.objects.create(
                tenant=tenant, customer=customer, request_id=inp.request_id,
                idempotency_key=inp.idempotency_key, metadata=inp.metadata,
                event_type=inp.event_type, provider=inp.provider,
                provider_cost_micros=provider_cost_micros,
                billed_cost_micros=billed_cost_micros,
                units=inp.units, currency=inp.currency,
                usage_metrics=inp.usage_metrics,
                pricing_provenance=provenance,
                product_id=inp.product_id, tags=inp.tags, task_id=inp.task_id,
                billing_owner_id=inp.billing_owner_id,
                service_id=inp.service_id, agent_id=inp.agent_id,
                **create_kwargs)
            if inp.task_id is not None:
                # One-rule: the ONE accumulate primitive — always records
                # both totals (the tipping event and everything after a
                # kill land, bill, and count) and returns crossing
                # verdicts instead of raising. The event create above and
                # this accumulate share the savepoint, so totals and
                # events can never diverge.
                from apps.platform.tasks.services import TaskService
                task, verdicts = TaskService.accumulate_cost(
                    inp.task_id, billed_cost_micros=billed_cost_micros,
                    provider_cost_micros=provider_cost_micros,
                    tenant_id=tenant.id, customer_id=customer.id)
        live = {}
        if inp.debit_live_counter:
            # Tier-2 (P2/WS1): maintain the synchronous live counter on the
            # SAME billing owner the async drawdown will debit. Reached only
            # once the event has committed to the savepoint (the
            # IntegrityError replay race propagates above, so a duplicate
            # never double-decrements). No-op when enforcement_mode is off.
            # Routed through the sanctioned billing read/port contract
            # (apps.billing.queries) — metering must not import a billing
            # internal directly (product-boundary ADR-001).
            from apps.billing.queries import record_live_usage_debit
            live = record_live_usage_debit(
                inp.billing_owner_id, tenant, billed_cost_micros,
                effective_at=inp.effective_at, now=inp.now) or {}
        # Stop-context tagging (#41): runs AFTER the live debit so a fresh
        # fast-lane crossing (stop_episode_opened) marks THIS event as the
        # episode's tipping event; still inside the lane's recording
        # transaction.
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
            billed_cost_micros=billed_cost_micros,
            event_type=inp.event_type, provider=inp.provider,
            task_id=str(inp.task_id) if inp.task_id else None,
            billing_owner_id=str(inp.billing_owner_id),
            # Normalized to UTC: the instance attribute keeps the caller's
            # original offset, but consumers bucket by UTC calendar month.
            effective_at=event.effective_at.astimezone(dt_timezone.utc).isoformat()))
        if verdicts is not None:
            from apps.platform.tasks import reasons
            kills = reasons.kill_plan(task.id, task.parent_id, verdicts)
            if kills:
                transaction.on_commit(
                    lambda: _execute_kills(kills, tenant_id=tenant.id,
                                           customer_id=customer.id))
        return RecordingOutcome(event, task, verdicts, live)

    @staticmethod
    @transaction.atomic
    def record_usage(tenant, customer, request_id, idempotency_key, *,
                     provider_cost_micros=None, billed_cost_micros=None, units=None,
                     provider="", event_type="", currency=None, tags=None,
                     product_id="", metadata=None, task_id=None, usage_metrics=None,
                     effective_at=None):
        """The sync lane (#112): validation + replay + owner resolve, then
        the ONE recording core. The 16-param keyword surface is kept verbatim
        — this is the input adapter every service-level call site and both
        sync endpoints already speak."""
        validate_tags(tags)
        existing = UsageEvent.objects.filter(
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
        tenant_currency = (tenant.default_currency or "usd").lower()
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
            usage_metrics=usage_metrics, tags=tags, product_id=product_id,
            task_id=task_id, units=units,
            caller_provider_cost=provider_cost_micros,
            caller_billed=billed_cost_micros, effective_at=effective_at,
            billing_owner_id=owner_id, owner_row=owner, now=now,
            debit_live_counter=True)
        try:
            outcome = UsageService._record_core(inp)
        except IntegrityError as exc:
            try:
                existing = UsageEvent.objects.get(
                    tenant=tenant, customer=customer, idempotency_key=idempotency_key)
            except UsageEvent.DoesNotExist:
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
            from apps.platform.tasks import reasons
            unit_reason, unit_scope = reasons.stop_fields(
                outcome.verdicts, is_subtask=task.parent_id is not None)
            if unit_reason is not None:
                stop, stop_reason, stop_scope = True, unit_reason, unit_scope
        return _result(outcome.event,
                       task_total_billed=task.total_billed_cost_micros if task else None,
                       task_total_provider=task.total_provider_cost_micros if task else None,
                       parent_task_id=task.parent_id if task else None,
                       stop=stop, stop_reason=stop_reason, stop_scope=stop_scope)

    @staticmethod
    def settle_raw(raw):
        """Exact-settle one accepted RawIngestEvent (Task 6) — the settle
        lane's input adapter over the ONE recording core (#112).

        This path NEVER rejects: it prices exactly, records durably, and
        adjusts the live counter by (estimate - exact). One-rule (#37):
        task-limit detection happens HERE, at settle, with exact costs —
        the one accumulate primitive returns crossing verdicts and the same
        kill flow + task.limit_exceeded event as the sync path is registered
        by the core on this transaction's on_commit. Signal latency for
        async unit limits is settle latency, by design (settle-time exact
        counting). Tier-ladder locks are worker-only contention here (the
        synchronous record_usage path never reaches this code, so no
        cross-path deadlock risk).

        Returns "settled" or "duplicate". Any OTHER exception (a poison
        payload — e.g. a strict-coverage PricingError) propagates UNCAUGHT;
        the caller (apps.metering.usage.tasks.settle_raw_events) owns the
        attempts/failed bookkeeping and hold release for that case.
        """
        from apps.billing.queries import settle_ingest_hold, release_ingest_hold

        tenant, customer = raw.tenant, raw.customer
        effective_at = None
        try:
            with transaction.atomic():
                # settle_raw_events's batch claim only SELECTs (it never marks
                # rows), so two overlapping task invocations can both claim the
                # same still-"pending" id. Re-locking the SPECIFIC row here and
                # rechecking status is the exactly-once guarantee for the
                # hold-adjustment side effects below: a racing settle that
                # already resolved this raw makes this a silent no-op.
                raw = RawIngestEvent.objects.select_for_update().get(id=raw.id)
                if raw.status != "pending":
                    return raw.status
                p = raw.payload
                effective_at = _parse_effective_at(p)
                # Stop-context owner state (#41): durable owner state only at
                # settle — there is no fast lane here, so no async event ever
                # claims a customer-floor tip (the crossing was detected at
                # accept/drawdown time between events). Owner row fetched
                # only when enforcement is on — the only mode whose durable
                # ledger can have state.
                from apps.platform.tenants.flags import enforcing
                owner_row = None
                if enforcing(tenant):
                    from apps.platform.customers.models import Customer
                    owner_row = Customer.objects.filter(
                        id=raw.billing_owner_id).only("id", "status").first()
                inp = RecordingInput.gather(
                    tenant=tenant, customer=customer,
                    request_id=p.get("request_id", ""),
                    idempotency_key=raw.idempotency_key,
                    metadata=p.get("metadata"),
                    event_type=p.get("event_type"),
                    provider=p.get("provider"),
                    usage_metrics=p.get("usage_metrics"), tags=p.get("tags"),
                    product_id=p.get("product_id"), task_id=raw.task_id,
                    units=p.get("units"),
                    caller_provider_cost=p.get("provider_cost_micros"),
                    caller_billed=p.get("billed_cost_micros"),
                    effective_at=effective_at,
                    # The owner was pinned at accept time — never re-resolved
                    # at settle.
                    billing_owner_id=raw.billing_owner_id, owner_row=owner_row,
                    now=timezone.now(),
                    debit_live_counter=False)
                outcome = UsageService._record_core(inp)
                raw.status = "settled"
                raw.save(update_fields=["status", "updated_at"])
        except IntegrityError:
            # The IntegrityError rolled the atomic back — RELEASING the row
            # lock taken at the top while the DB status is still "pending" —
            # so a second settle_raw_events invocation that claimed this same
            # id can be racing us right here. Resolve under a FRESH lock and
            # let only the winner (the pending -> duplicate flip) release the
            # hold: a hold release is a Redis credit, so a double release
            # would over-credit the live gate (over-permissive — the worst
            # failure direction). Redis effects stay post-commit, mirroring
            # the settled path.
            with transaction.atomic():
                locked = RawIngestEvent.objects.select_for_update().get(id=raw.id)
                if locked.status != "pending":
                    # A racer already resolved (and, if held, released) it.
                    return locked.status
                locked.status = "duplicate"
                locked.save(update_fields=["status", "updated_at"])
            if locked.held:
                release_ingest_hold(locked.billing_owner_id, tenant,
                                    locked.estimate_micros, effective_at=effective_at)
            return "duplicate"
        # One-rule (#37): the async kill parity now rides the recording core —
        # a crossing verdict registered the SAME kill flow (reasons.kill_plan
        # → kill_and_announce) on the settle transaction's on_commit, so the
        # kills have already fired by the time the true-up below runs — the
        # exact order the inline kill loop used to guarantee here.
        if raw.held:
            # A hold that was really taken ALWAYS trues up — including after
            # an ON→OFF arrival-signals flip (#46 §E: "outstanding holds
            # drain at settle"), so the counter converges instead of being
            # wedged low until the TTL.
            settle_ingest_hold(raw.billing_owner_id, tenant,
                               raw.estimate_micros - outcome.event.billed_cost_micros,
                               effective_at=effective_at)
        else:
            from apps.platform.tenants.flags import arrival_signals_on
            if arrival_signals_on(tenant):
                # idem-hit at accept took NO hold (held=False). If the first
                # append had already settled, THIS attempt hits IntegrityError
                # above and returns "duplicate" without reaching here. If the
                # first append was LOST (crash between hold and append), this
                # row is the only survivor and the orphaned hold already
                # decremented the live counter once — this full debit
                # double-counts against that orphan. Documented, NOT fixed
                # here (spec invariant 7 — corrected wording): the hourly
                # prepaid reconcile MIN-merge does NOT correct this — it only
                # ever LOWERS toward the durable balance, and the orphan has
                # already made the live counter LOWER than durable, so
                # reconcile finds it already at (or below) target and leaves
                # it untouched (a fixed point, not a correction). The drift
                # persists (bounded, over-restrictive, DRIFT_ALERT_MICROS-
                # visible) until a credit/top-up, the enforcement-transition
                # cleanup, or the 62-day TTL heals it; see test_settlement.py's
                # orphan-hold pin.
                # Rows accepted while arrival signals were OFF land here too
                # once the lane is back ON: the full debit keeps the freshly
                # re-seeded counter honest for spend the seed missed.
                settle_ingest_hold(raw.billing_owner_id, tenant,
                                   -outcome.event.billed_cost_micros,
                                   effective_at=effective_at)
            # Arrival signals OFF (#46 §E): no debit — the fast lane is off
            # as one unit, and this write would otherwise CREATE the postpaid
            # livespend key (INCRBY) and quietly maintain a fast-lane counter
            # whose MAX-merge is switched off. Nothing reads the counter in
            # the OFF posture; the OFF→ON reconcile re-seeds it from durable
            # truth.
        return "settled"
