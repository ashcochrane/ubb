import logging

from django.db import transaction, IntegrityError

from apps.metering.usage.models import UsageEvent
from apps.platform.events.outbox import write_event
from apps.platform.events.schemas import UsageRecorded

logger = logging.getLogger(__name__)


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
        group=None,
        run_id=None,
    ):

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
                "run_id": str(existing.run_id) if existing.run_id else None,
                "run_total_cost_micros": None,
                "hard_stop": False,
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
                    group=group,
                )
            )
            cost_micros = billed_cost_micros

        # 2.5 Run hard-stop check (synchronous, under select_for_update)
        run = None
        if run_id is not None:
            from apps.platform.runs.services import RunService

            effective_cost_for_run = (
                billed_cost_micros if billed_cost_micros is not None else cost_micros
            )
            # Locks the Run row, increments cost, checks both hard stop limits.
            # Raises HardStopExceeded if either limit is breached — the outer
            # @transaction.atomic rolls back, no event is created, and the
            # caller (endpoint) handles killing the run in a separate transaction.
            run = RunService.accumulate_cost(run_id, effective_cost_for_run or 0)

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
                    group=group,
                    run_id=run_id,
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
                "run_id": str(existing.run_id) if existing.run_id else None,
                "run_total_cost_micros": None,
                "hard_stop": False,
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
            run_id=str(run_id) if run_id else None,
        ))

        return {
            "event_id": str(event.id),
            "new_balance_micros": None,
            "suspended": False,
            "provider_cost_micros": provider_cost_micros,
            "billed_cost_micros": billed_cost_micros,
            "run_id": str(run_id) if run_id else None,
            "run_total_cost_micros": run.total_cost_micros if run else None,
            "hard_stop": False,
        }
