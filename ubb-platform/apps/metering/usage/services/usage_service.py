import logging
import re
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


def _result(event, *, task_total_billed=None, task_total_provider=None,
            stop=False, stop_reason=None, stop_scope=None,
            suspended=False, new_balance_micros=None):
    """Build the record_usage response.

    One-rule (#37): every recorded event answers success; the stop
    instruction rides these fields. The named task's BOTH running totals
    travel, denominationally explicit. parent_task_id is always null until
    the subtask ticket lands.

    Tier-2 (D5/I4): the customer-wide spend-stop verdict travels on EVERY
    return path of record_usage — the happy path AND both idempotent-replay
    returns — so a replayed event for an already-stopped owner never reports
    "all clear".
    """
    return {
        "event_id": str(event.id),
        "provider_cost_micros": event.provider_cost_micros,
        "billed_cost_micros": event.billed_cost_micros,
        "units": event.units,
        "new_balance_micros": new_balance_micros, "suspended": suspended,
        "task_id": str(event.task_id) if event.task_id else None,
        "parent_task_id": None,
        "task_total_billed_cost_micros": task_total_billed,
        "task_total_provider_cost_micros": task_total_provider,
        "stop": stop, "stop_reason": stop_reason, "stop_scope": stop_scope,
        "usage_metrics": event.usage_metrics,
        "pricing_provenance": event.pricing_provenance,
        "service_id": event.service_id,
        "agent_id": event.agent_id,
    }


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
    from apps.platform.tenants.flags import enforcement_on
    if not enforcement_on(tenant):
        return {}
    from apps.billing.queries import read_live_stop
    return read_live_stop(customer.resolve_billing_owner().id, tenant)


class UsageService:
    @staticmethod
    @transaction.atomic
    def record_usage(tenant, customer, request_id, idempotency_key, *,
                     provider_cost_micros=None, billed_cost_micros=None, units=None,
                     provider="", event_type="", currency=None, tags=None,
                     product_id="", metadata=None, task_id=None, usage_metrics=None,
                     effective_at=None):
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
        # pinned billing_owner_id both key on the same resolver result.
        owner_id = customer.resolve_billing_owner().id
        if effective_at is not None:
            validate_effective_at(tenant, owner_id, effective_at, now)
        # CUR-1 choke point: every event is denominated in the tenant's single
        # currency. A caller-supplied currency must MATCH it (case-insensitive)
        # or the event is rejected — no FX, no mixed-currency data. Stored
        # normalized lowercase.
        tenant_currency = (tenant.default_currency or "usd").lower()
        if currency:
            currency = str(currency).strip().lower()
            if currency != tenant_currency:
                raise ValueError(
                    f"currency mismatch: event currency {currency!r} does not "
                    f"match tenant currency {tenant_currency!r} (per-tenant "
                    "single currency; multi-currency/FX is not supported)")
        currency = tenant_currency
        from apps.metering.pricing.services.pricing_service import PricingService
        _tags = tags or {}
        service_id = _tags.get("service", "")
        agent_id = _tags.get("agent", "")
        # Tags are analytics-only labels (#37): the task_id request field is
        # the ONLY unit attribution — no tag-fallback inference, no label cap.
        if not product_id:
            product_id = _tags.get("product", "") or ""
        task = None
        verdicts = None
        try:
            with transaction.atomic():
                # as_of=effective_at prices on the card versions valid at the
                # EFFECTIVE time.
                provider_cost_micros, billed_cost_micros, provenance = PricingService.price(
                    tenant=tenant, customer=customer, event_type=event_type or "",
                    provider=provider or "", usage_metrics=usage_metrics, tags=tags,
                    currency=currency, caller_provider_cost=provider_cost_micros,
                    caller_billed=billed_cost_micros, units=units,
                    as_of=effective_at)
                create_kwargs = {}
                if effective_at is not None:
                    create_kwargs["effective_at"] = effective_at
                event = UsageEvent.objects.create(
                    tenant=tenant, customer=customer, request_id=request_id,
                    idempotency_key=idempotency_key, metadata=metadata or {},
                    event_type=event_type or "", provider=provider or "",
                    provider_cost_micros=provider_cost_micros,
                    billed_cost_micros=billed_cost_micros,
                    units=units, currency=currency, usage_metrics=usage_metrics or {},
                    pricing_provenance=provenance,
                    product_id=product_id or "", tags=tags, task_id=task_id,
                    billing_owner_id=owner_id,
                    service_id=service_id, agent_id=agent_id, **create_kwargs)
                if task_id is not None:
                    # One-rule: the ONE accumulate primitive — always records
                    # both totals (the tipping event and everything after a
                    # kill land, bill, and count) and returns crossing
                    # verdicts instead of raising. The event create above and
                    # this accumulate share the savepoint, so totals and
                    # events can never diverge.
                    from apps.platform.tasks.services import TaskService
                    task, verdicts = TaskService.accumulate_cost(
                        task_id, billed_cost_micros=billed_cost_micros,
                        provider_cost_micros=provider_cost_micros,
                        tenant_id=tenant.id, customer_id=customer.id)
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
        # Tier-2 (P2/WS1): maintain the synchronous live counter on the SAME
        # billing owner the async drawdown will debit. Reached only once the
        # event has committed to the savepoint (the IntegrityError replay race
        # returns above, so a duplicate never double-decrements). Write-only in
        # P2 — the returned verdict is ignored here; P3 threads it into _result.
        # No-op when enforcement_mode is off. Routed through the sanctioned
        # billing read/port contract (apps.billing.queries) — metering must not
        # import a billing internal directly (product-boundary ADR-001).
        from apps.billing.queries import record_live_usage_debit
        live = record_live_usage_debit(
            owner_id, tenant, billed_cost_micros, effective_at=effective_at, now=now) or {}
        if effective_at is not None:
            eff_month_start = month_bounds(effective_at)[0]
            if eff_month_start < month_bounds(now)[0]:
                # Backfill into a PRIOR month: mark the period dirty so the
                # hourly resnapshot task refreshes its margin snapshot. Same
                # transaction as the event; savepoint-IntegrityError-swallow
                # (billing/handlers.py pattern) absorbs the unique-marker race.
                try:
                    with transaction.atomic():
                        BackfillDirtyPeriod.objects.create(
                            tenant=tenant, customer=customer,
                            period_start=eff_month_start)
                except IntegrityError:
                    pass  # marker already pending for this (tenant, customer, period)
        write_event(UsageRecorded(
            tenant_id=str(tenant.id), customer_id=str(customer.id), event_id=str(event.id),
            cost_micros=billed_cost_micros, provider_cost_micros=provider_cost_micros,
            billed_cost_micros=billed_cost_micros, event_type=event_type or "",
            provider=provider or "", task_id=str(task_id) if task_id else None,
            billing_owner_id=str(owner_id),
            # Normalized to UTC: the instance attribute keeps the caller's
            # original offset, but consumers bucket by UTC calendar month.
            effective_at=event.effective_at.astimezone(dt_timezone.utc).isoformat()))
        # Stop-verdict fields: a task-scoped verdict (the most specific scope)
        # wins the scalar slot; the customer-wide verdict fills it otherwise.
        # A simultaneous customer-wide stop still surfaces on the next ack
        # (and via stop.fired); the itemized multi-limit story is the
        # past-limit ticket's stop_context array.
        stop = live.get("stop", False)
        stop_reason = live.get("stop_reason")
        stop_scope = live.get("stop_scope")
        if verdicts is not None:
            from apps.platform.tasks import reasons
            if verdicts["crossed_task_limit"]:
                stop, stop_reason, stop_scope = True, reasons.TASK_LIMIT, "task"
            elif verdicts["crossed_floor_snapshot"]:
                stop, stop_reason, stop_scope = True, reasons.CUSTOMER_FLOOR, "task"
            elif verdicts["task_not_active"]:
                stop, stop_reason, stop_scope = True, reasons.TASK_NOT_ACTIVE, "task"
        return _result(event,
                       task_total_billed=task.total_billed_cost_micros if task else None,
                       task_total_provider=task.total_provider_cost_micros if task else None,
                       stop=stop, stop_reason=stop_reason, stop_scope=stop_scope)

    @staticmethod
    def settle_raw(raw):
        """Exact-settle one accepted RawIngestEvent (Task 6).

        This path NEVER rejects: it prices exactly, records durably, and
        adjusts the live counter by (estimate - exact). One-rule (#37):
        task-limit detection happens HERE, at settle, with exact costs —
        the one accumulate primitive returns crossing verdicts and the same
        idempotent kill flow + task.limit_exceeded event as the sync path
        runs after the settle commits. Signal latency for async unit limits
        is settle latency, by design (settle-time exact counting).
        Tier-ladder locks are worker-only contention here (the synchronous
        record_usage path never reaches this code, so no cross-path deadlock
        risk).

        Returns "settled" or "duplicate". Any OTHER exception (a poison
        payload — e.g. a strict-coverage PricingError) propagates UNCAUGHT;
        the caller (apps.metering.usage.tasks.settle_raw_events) owns the
        attempts/failed bookkeeping and hold release for that case.
        """
        from apps.billing.queries import settle_ingest_hold, release_ingest_hold
        from apps.metering.pricing.services.pricing_service import PricingService
        from apps.platform.tasks.services import TaskService

        tenant, customer = raw.tenant, raw.customer
        verdicts = None
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
                as_of = effective_at or timezone.now()
                tags = p.get("tags")
                _tags = tags or {}
                service_id = _tags.get("service", "")
                agent_id = _tags.get("agent", "")
                product_id = p.get("product_id") or _tags.get("product", "") or ""
                currency = (tenant.default_currency or "usd").lower()
                provider_cost_micros, billed_cost_micros, provenance = PricingService.price(
                    tenant=tenant, customer=customer,
                    event_type=p.get("event_type") or "", provider=p.get("provider") or "",
                    usage_metrics=p.get("usage_metrics"), tags=tags,
                    currency=currency, caller_provider_cost=p.get("provider_cost_micros"),
                    caller_billed=p.get("billed_cost_micros"), units=p.get("units"),
                    as_of=as_of)
                create_kwargs = {}
                if effective_at is not None:
                    create_kwargs["effective_at"] = effective_at
                event = UsageEvent.objects.create(
                    tenant=tenant, customer=customer,
                    request_id=p.get("request_id", ""),
                    idempotency_key=raw.idempotency_key,
                    metadata=p.get("metadata") or {},
                    event_type=p.get("event_type") or "", provider=p.get("provider") or "",
                    provider_cost_micros=provider_cost_micros,
                    billed_cost_micros=billed_cost_micros,
                    units=p.get("units"), currency=currency,
                    usage_metrics=p.get("usage_metrics") or {},
                    pricing_provenance=provenance,
                    product_id=product_id, tags=tags, task_id=raw.task_id,
                    billing_owner_id=raw.billing_owner_id,
                    service_id=service_id, agent_id=agent_id, **create_kwargs)
                if raw.task_id:
                    # The ONE accumulate primitive — a settle landing after
                    # the task was killed/completed still records the TRUE
                    # costs against both totals (task_not_active is a
                    # verdict, never a refusal); a crossing verdict drives
                    # the kill flow after this transaction commits.
                    _, verdicts = TaskService.accumulate_cost(
                        raw.task_id, billed_cost_micros=billed_cost_micros,
                        provider_cost_micros=provider_cost_micros,
                        tenant_id=tenant.id, customer_id=customer.id)
                if effective_at is not None:
                    eff_month_start = month_bounds(effective_at)[0]
                    if eff_month_start < month_bounds(timezone.now())[0]:
                        # Backfill into a PRIOR month: same marker + swallow
                        # pattern as record_usage.
                        try:
                            with transaction.atomic():
                                BackfillDirtyPeriod.objects.create(
                                    tenant=tenant, customer=customer,
                                    period_start=eff_month_start)
                        except IntegrityError:
                            pass
                write_event(UsageRecorded(
                    tenant_id=str(tenant.id), customer_id=str(customer.id),
                    event_id=str(event.id),
                    cost_micros=billed_cost_micros, provider_cost_micros=provider_cost_micros,
                    billed_cost_micros=billed_cost_micros, event_type=p.get("event_type") or "",
                    provider=p.get("provider") or "",
                    task_id=str(raw.task_id) if raw.task_id else None,
                    billing_owner_id=str(raw.billing_owner_id),
                    effective_at=event.effective_at.astimezone(dt_timezone.utc).isoformat()))
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
        # One-rule (#37): the async kill parity — a crossing verdict at settle
        # drives the SAME idempotent kill flow + task.limit_exceeded event as
        # the sync path, in its own transaction, after the settle committed.
        if verdicts is not None:
            from apps.platform.tasks import reasons
            if verdicts["crossed_task_limit"]:
                TaskService.kill_and_announce(
                    raw.task_id, reasons.TASK_LIMIT,
                    tenant_id=tenant.id, customer_id=customer.id)
            elif verdicts["crossed_floor_snapshot"]:
                TaskService.kill_and_announce(
                    raw.task_id, reasons.CUSTOMER_FLOOR,
                    tenant_id=tenant.id, customer_id=customer.id)
        if raw.held:
            settle_ingest_hold(raw.billing_owner_id, tenant,
                               raw.estimate_micros - billed_cost_micros,
                               effective_at=effective_at)
        else:
            # idem-hit at accept took NO hold (held=False). If the first
            # append had already settled, THIS attempt hits IntegrityError
            # above and returns "duplicate" without reaching here. If the
            # first append was LOST (crash between hold and append), this row
            # is the only survivor and the orphaned hold already decremented
            # the live counter once — this full debit double-counts against
            # that orphan. Documented, NOT fixed here (spec invariant 7 —
            # corrected wording): the hourly reconcile_prepaid MIN-merge does
            # NOT correct this — it only ever LOWERS toward the durable
            # balance, and the orphan has already made the live counter LOWER
            # than durable, so reconcile finds it already at (or below) target
            # and leaves it untouched (a fixed point, not a correction). The
            # drift persists (bounded, over-restrictive, DRIFT_ALERT_MICROS-
            # visible) until a credit/top-up, cleanup_keys, or the 62-day TTL
            # heals it; see test_settlement.py's orphan-hold pin.
            settle_ingest_hold(raw.billing_owner_id, tenant,
                               -billed_cost_micros, effective_at=effective_at)
        return "settled"
