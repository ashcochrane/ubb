import logging
import re

from django.db import transaction, IntegrityError

from apps.metering.usage.models import UsageEvent
from apps.platform.events.outbox import write_event
from apps.platform.events.schemas import UsageRecorded

logger = logging.getLogger(__name__)

# Min 2 chars, max 64 chars, starts with letter, lowercase alphanumeric + underscores
TAG_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]{1,63}$')


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
                     product_id="", metadata=None, run_id=None, usage_metrics=None):
        validate_tags(tags)
        existing = UsageEvent.objects.filter(
            tenant=tenant, customer=customer, idempotency_key=idempotency_key).first()
        if existing:
            return _result(existing, run_total=None)
        currency = currency or tenant.default_currency
        from apps.metering.pricing.services.pricing_service import PricingService
        _tags = tags or {}
        service_id = _tags.get("service", "")
        agent_id = _tags.get("agent", "")
        if not product_id:
            product_id = _tags.get("product", "") or ""
        run = None
        owner_id = customer.resolve_billing_owner().id
        try:
            with transaction.atomic():
                # Pricing runs INSIDE the savepoint: tiered price cards advance
                # the period ladder (PricingPeriodCounter) under a row lock, so
                # a raced duplicate insert below must roll the advance back too.
                provider_cost_micros, billed_cost_micros, provenance = PricingService.price(
                    tenant=tenant, customer=customer, event_type=event_type or "",
                    provider=provider or "", usage_metrics=usage_metrics, tags=tags,
                    currency=currency, caller_provider_cost=provider_cost_micros,
                    caller_billed=billed_cost_micros, units=units)
                if run_id is not None:
                    from apps.platform.runs.services import RunService
                    run = RunService.accumulate_cost(
                        run_id, billed_cost_micros,
                        tenant_id=tenant.id, customer_id=customer.id)
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
                    service_id=service_id, agent_id=agent_id)
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
        write_event(UsageRecorded(
            tenant_id=str(tenant.id), customer_id=str(customer.id), event_id=str(event.id),
            cost_micros=billed_cost_micros, provider_cost_micros=provider_cost_micros,
            billed_cost_micros=billed_cost_micros, event_type=event_type or "",
            provider=provider or "", run_id=str(run_id) if run_id else None,
            billing_owner_id=str(owner_id)))
        return _result(event, run_total=run.total_cost_micros if run else None)
