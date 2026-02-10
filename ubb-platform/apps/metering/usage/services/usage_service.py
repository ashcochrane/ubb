import logging
import re

from django.db import transaction, IntegrityError

from apps.metering.usage.models import UsageEvent
from apps.platform.events.outbox import write_event
from apps.platform.events.schemas import UsageRecorded

logger = logging.getLogger(__name__)

# Min 2 chars, max 64 chars, starts with letter, lowercase alphanumeric + underscores
GROUP_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]{1,63}$')


def validate_group_keys(group_keys):
    """Validate group_keys dict. Raises ValueError on invalid input."""
    if group_keys is None:
        return
    if not isinstance(group_keys, dict):
        raise ValueError("group_keys must be a dict")
    if len(group_keys) > 10:
        raise ValueError("group_keys cannot have more than 10 keys")
    for key, value in group_keys.items():
        if not GROUP_KEY_PATTERN.match(key):
            raise ValueError(
                f"group_keys key '{key}' must be lowercase alphanumeric + underscores, "
                "start with a letter, 2-64 chars"
            )
        if not isinstance(value, str):
            raise ValueError(f"group_keys value for '{key}' must be a string")
        if len(value) > 256:
            raise ValueError(f"group_keys value for '{key}' exceeds 256 chars")


class UsageService:
    @staticmethod
    @transaction.atomic
    def record_usage(
        tenant,
        customer,
        request_id,
        idempotency_key,
        cost_micros=None,
        metadata=None,
        event_type=None,
        provider=None,
        usage_metrics=None,
        properties=None,
        group_keys=None,
    ):
        # 0. Validate group_keys before any DB work
        validate_group_keys(group_keys)

        # 1. Idempotency check — fast path, no wallet lookup needed
        existing = UsageEvent.objects.filter(
            tenant=tenant, customer=customer, idempotency_key=idempotency_key
        ).first()
        if existing:
            return {
                "event_id": str(existing.id),
                "new_balance_micros": None,
                "suspended": False,
                "provider_cost_micros": existing.provider_cost_micros,
                "billed_cost_micros": existing.billed_cost_micros,
            }

        # 2. Price the event if raw metrics provided
        provider_cost_micros = None
        billed_cost_micros = None
        pricing_provenance = {}

        if usage_metrics is not None:
            from apps.metering.pricing.services.pricing_service import PricingService
            provider_cost_micros, billed_cost_micros, pricing_provenance = (
                PricingService.price_event(
                    tenant=tenant,
                    event_type=event_type,
                    provider=provider,
                    usage_metrics=usage_metrics,
                    properties=properties,
                )
            )
            cost_micros = billed_cost_micros

        # 3. Create event (handle race via IntegrityError)
        try:
            with transaction.atomic():  # savepoint
                event = UsageEvent.objects.create(
                    tenant=tenant,
                    customer=customer,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    cost_micros=cost_micros,
                    balance_after_micros=None,
                    metadata=metadata or {},
                    event_type=event_type or "",
                    provider=provider or "",
                    usage_metrics=usage_metrics or {},
                    properties=properties or {},
                    provider_cost_micros=provider_cost_micros,
                    billed_cost_micros=billed_cost_micros,
                    pricing_provenance=pricing_provenance,
                    group_keys=group_keys,
                )
        except IntegrityError:
            existing = UsageEvent.objects.get(
                tenant=tenant, customer=customer, idempotency_key=idempotency_key
            )
            return {
                "event_id": str(existing.id),
                "new_balance_micros": None,
                "suspended": False,
                "provider_cost_micros": existing.provider_cost_micros,
                "billed_cost_micros": existing.billed_cost_micros,
            }

        # 4. Compute effective cost for outbox event
        # billed_cost_micros is set for metric-priced events; cost_micros is the fallback
        # for legacy caller-provided cost mode.
        effective_cost = billed_cost_micros if billed_cost_micros is not None else cost_micros

        # 5. Write outbox event for cross-product handlers
        # Billing's outbox handler will handle wallet deduction, suspension, and auto-topup.
        write_event(UsageRecorded(
            tenant_id=str(tenant.id),
            customer_id=str(customer.id),
            event_id=str(event.id),
            cost_micros=effective_cost,
            provider_cost_micros=provider_cost_micros,
            billed_cost_micros=billed_cost_micros,
            event_type=event_type or "",
            provider=provider or "",
        ))

        return {
            "event_id": str(event.id),
            "new_balance_micros": None,
            "suspended": False,
            "provider_cost_micros": provider_cost_micros,
            "billed_cost_micros": billed_cost_micros,
        }
