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
    }


class UsageService:
    @staticmethod
    @transaction.atomic
    def record_usage(tenant, customer, request_id, idempotency_key, *,
                     provider_cost_micros, billed_cost_micros=None, units=None,
                     provider="", event_type="", currency=None, tags=None,
                     product_id="", metadata=None, run_id=None):
        validate_tags(tags)
        existing = UsageEvent.objects.filter(
            tenant=tenant, customer=customer, idempotency_key=idempotency_key).first()
        if existing:
            return _result(existing, run_total=None)
        from apps.metering.pricing.services.markup_service import MarkupService
        if billed_cost_micros is None:
            billed_cost_micros = MarkupService.apply(provider_cost_micros, tenant=tenant, customer=customer)
        run = None
        if run_id is not None:
            from apps.platform.runs.services import RunService
            run = RunService.accumulate_cost(run_id, billed_cost_micros)
        try:
            with transaction.atomic():
                event = UsageEvent.objects.create(
                    tenant=tenant, customer=customer, request_id=request_id,
                    idempotency_key=idempotency_key, metadata=metadata or {},
                    event_type=event_type or "", provider=provider or "",
                    provider_cost_micros=provider_cost_micros,
                    billed_cost_micros=billed_cost_micros,
                    units=units, currency=currency or tenant.default_currency,
                    product_id=product_id or "", tags=tags, run_id=run_id)
        except IntegrityError:
            existing = UsageEvent.objects.get(
                tenant=tenant, customer=customer, idempotency_key=idempotency_key)
            return _result(existing, run_total=None)
        write_event(UsageRecorded(
            tenant_id=str(tenant.id), customer_id=str(customer.id), event_id=str(event.id),
            cost_micros=billed_cost_micros, provider_cost_micros=provider_cost_micros,
            billed_cost_micros=billed_cost_micros, event_type=event_type or "",
            provider=provider or "", run_id=str(run_id) if run_id else None))
        return _result(event, run_total=run.total_cost_micros if run else None)
