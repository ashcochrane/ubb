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
        usage_metrics=None,
        properties=None,
        group=None,
        run_id=None,
        pricing_card=None,
    ):
        # 1. Idempotency fast path
        existing = UsageEvent.objects.filter(
            tenant=tenant, customer=customer, idempotency_key=idempotency_key,
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

        # 2. Price via slug (the only supported path)
        provider_cost_micros = None
        billed_cost_micros = None
        pricing_provenance = {}
        card_obj = None
        card_slug = ""
        card_name = ""
        provider = ""

        if pricing_card is not None and usage_metrics is not None:
            from apps.metering.pricing.services.pricing_service import PricingService
            (
                provider_cost_micros,
                billed_cost_micros,
                pricing_provenance,
                card_obj,
            ) = PricingService.price_event_by_slug(
                tenant=tenant,
                card_slug=pricing_card,
                usage_metrics=usage_metrics,
                group=group,
            )
            cost_micros = billed_cost_micros
            if card_obj is not None:
                card_slug = card_obj.slug
                card_name = card_obj.name
                provider = card_obj.provider
        elif usage_metrics is not None:
            raise ValueError("pricing_card is required when usage_metrics is provided")

        # 3. Run hard-stop accumulation
        run = None
        if run_id is not None:
            from apps.platform.runs.services import RunService

            effective_cost_for_run = (
                billed_cost_micros if billed_cost_micros is not None else cost_micros
            )
            run = RunService.accumulate_cost(run_id, effective_cost_for_run or 0)

        # 4. Create event
        try:
            with transaction.atomic():
                event = UsageEvent.objects.create(
                    tenant=tenant,
                    customer=customer,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    cost_micros=cost_micros,
                    balance_after_micros=None,
                    metadata=metadata or {},
                    provider=provider,
                    usage_metrics=usage_metrics or {},
                    properties=properties or {},
                    provider_cost_micros=provider_cost_micros,
                    billed_cost_micros=billed_cost_micros,
                    pricing_provenance=pricing_provenance,
                    group=group,
                    run_id=run_id,
                    card=card_obj,
                    card_slug=card_slug,
                    card_name=card_name,
                )
        except IntegrityError:
            existing = UsageEvent.objects.get(
                tenant=tenant, customer=customer, idempotency_key=idempotency_key,
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

        # 5. Outbox
        effective_cost = billed_cost_micros if billed_cost_micros is not None else cost_micros
        write_event(UsageRecorded(
            tenant_id=str(tenant.id),
            customer_id=str(customer.id),
            event_id=str(event.id),
            cost_micros=effective_cost,
            provider_cost_micros=provider_cost_micros,
            billed_cost_micros=billed_cost_micros,
            provider=provider,
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
