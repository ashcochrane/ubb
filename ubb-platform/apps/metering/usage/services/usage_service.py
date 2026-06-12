import logging
import re
from datetime import timedelta, timezone as dt_timezone

from django.db import transaction, IntegrityError
from django.utils import timezone

from apps.metering.pricing.services.tier_counter_service import month_bounds
from apps.metering.usage.models import BackfillDirtyPeriod, UsageEvent
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


def _result(event, run_total):
    return {
        "event_id": str(event.id),
        "provider_cost_micros": event.provider_cost_micros,
        "billed_cost_micros": event.billed_cost_micros,
        "units": event.units,
        "new_balance_micros": None, "suspended": False,
        "run_id": str(event.run_id) if event.run_id else None,
        "run_total_cost_micros": run_total, "hard_stop": False,
        "usage_metrics": event.usage_metrics,
        "pricing_provenance": event.pricing_provenance,
        "service_id": event.service_id,
        "agent_id": event.agent_id,
    }


class UsageService:
    @staticmethod
    @transaction.atomic
    def record_usage(tenant, customer, request_id, idempotency_key, *,
                     provider_cost_micros=None, billed_cost_micros=None, units=None,
                     provider="", event_type="", currency=None, tags=None,
                     product_id="", metadata=None, run_id=None, usage_metrics=None,
                     effective_at=None):
        validate_tags(tags)
        existing = UsageEvent.objects.filter(
            tenant=tenant, customer=customer, idempotency_key=idempotency_key).first()
        if existing:
            # Replay wins BEFORE effective_at validation: a whole-batch retry
            # must return the original event even if the window has since aged
            # past the timestamp or the period closed.
            return _result(existing, run_total=None)
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
        if not product_id:
            product_id = _tags.get("product", "") or ""
        run = None
        try:
            with transaction.atomic():
                # Pricing runs INSIDE the savepoint: tiered price cards advance
                # the period ladder (PricingPeriodCounter) under a row lock, so
                # a raced duplicate insert below must roll the advance back too.
                # as_of=effective_at prices on the card versions valid at the
                # EFFECTIVE time and advances the EFFECTIVE month's tier ladder.
                provider_cost_micros, billed_cost_micros, provenance = PricingService.price(
                    tenant=tenant, customer=customer, event_type=event_type or "",
                    provider=provider or "", usage_metrics=usage_metrics, tags=tags,
                    currency=currency, caller_provider_cost=provider_cost_micros,
                    caller_billed=billed_cost_micros, units=units,
                    as_of=effective_at)
                if run_id is not None:
                    from apps.platform.runs.services import RunService
                    run = RunService.accumulate_cost(
                        run_id, billed_cost_micros,
                        tenant_id=tenant.id, customer_id=customer.id)
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
                    product_id=product_id or "", tags=tags, run_id=run_id,
                    billing_owner_id=owner_id,
                    service_id=service_id, agent_id=agent_id, **create_kwargs)
        except IntegrityError as exc:
            try:
                existing = UsageEvent.objects.get(
                    tenant=tenant, customer=customer, idempotency_key=idempotency_key)
            except UsageEvent.DoesNotExist:
                # Not the idempotency duplicate — some other insert inside the
                # savepoint failed (counter/run machinery). Surface the original
                # IntegrityError attributably instead of masking it as a replay
                # (or as an unexplained DoesNotExist).
                raise exc
            return _result(existing, run_total=None)
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
            provider=provider or "", run_id=str(run_id) if run_id else None,
            billing_owner_id=str(owner_id),
            # Normalized to UTC: the instance attribute keeps the caller's
            # original offset, but consumers bucket by UTC calendar month.
            effective_at=event.effective_at.astimezone(dt_timezone.utc).isoformat()))
        return _result(event, run_total=run.total_cost_micros if run else None)
