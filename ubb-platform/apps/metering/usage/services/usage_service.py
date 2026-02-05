import logging
import re

from django.db import transaction, IntegrityError

from apps.metering.usage.models import UsageEvent
from apps.platform.customers.models import Wallet, WalletTransaction
from core.locking import lock_for_billing

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

        # 1. Idempotency check — fast path before locking
        existing = UsageEvent.objects.filter(
            tenant=tenant, customer=customer, idempotency_key=idempotency_key
        ).first()
        if existing:
            wallet = Wallet.objects.get(customer=customer)
            return {
                "event_id": str(existing.id),
                "new_balance_micros": existing.balance_after_micros if existing.balance_after_micros is not None else wallet.balance_micros,
                "suspended": customer.status == "suspended",
                "provider_cost_micros": existing.provider_cost_micros,
                "billed_cost_micros": existing.billed_cost_micros,
            }

        # 2. Lock wallet + customer in canonical order
        wallet, customer = lock_for_billing(customer.id)

        # 2b. Price the event if raw metrics provided
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
            cost_micros = billed_cost_micros  # Wallet deduction = billed cost

        # 3. Compute new balance before event creation
        new_balance = wallet.balance_micros - cost_micros

        # 4. Create event (handle race via IntegrityError)
        try:
            with transaction.atomic():  # savepoint
                event = UsageEvent.objects.create(
                    tenant=tenant,
                    customer=customer,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    cost_micros=cost_micros,
                    balance_after_micros=new_balance,
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
            existing = UsageEvent.objects.get(tenant=tenant, customer=customer, idempotency_key=idempotency_key)
            return {
                "event_id": str(existing.id),
                "new_balance_micros": existing.balance_after_micros if existing.balance_after_micros is not None else wallet.balance_micros,
                "suspended": customer.status == "suspended",
                "provider_cost_micros": existing.provider_cost_micros,
                "billed_cost_micros": existing.billed_cost_micros,
            }

        # 5. Deduct wallet (already locked via select_for_update)
        wallet.balance_micros = new_balance
        wallet.save(update_fields=["balance_micros", "updated_at"])

        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="USAGE_DEDUCTION",
            amount_micros=-cost_micros,
            balance_after_micros=wallet.balance_micros,
            description=f"Usage: {request_id}",
            reference_id=str(event.id),
        )

        # 5b. Accumulate usage for tenant billing (synchronous — atomic UPDATE is fast)
        # billed_cost_micros is set for metric-priced events; cost_micros is the fallback
        # for legacy caller-provided cost mode.
        effective_cost = billed_cost_micros if billed_cost_micros is not None else cost_micros
        from apps.tenant_billing.services import TenantBillingService
        try:
            TenantBillingService.accumulate_usage(tenant, effective_cost)
        except Exception:
            logger.exception(
                "Failed to accumulate tenant usage",
                extra={"data": {"tenant_id": str(tenant.id)}},
            )

        # 6. Check arrears threshold — customer already locked
        suspended = False
        threshold = customer.get_arrears_threshold()
        if wallet.balance_micros < -threshold:
            customer.status = "suspended"
            customer.save(update_fields=["status", "updated_at"])
            suspended = True

        # 7. Auto top-up check — creates pending attempt if eligible
        attempt = None
        from apps.metering.usage.services.auto_topup_service import AutoTopUpService
        try:
            attempt = AutoTopUpService.create_pending_attempt(customer, wallet)
        except Exception:
            logger.exception(
                "Auto top-up check failed",
                extra={"data": {"customer_id": str(customer.id)}},
            )

        # 8. Dispatch charge task after commit
        if attempt is not None:
            from apps.metering.usage.tasks import charge_auto_topup_task
            transaction.on_commit(
                lambda aid=attempt.id: charge_auto_topup_task.delay(aid)
            )

        return {
            "event_id": str(event.id),
            "new_balance_micros": wallet.balance_micros,
            "suspended": suspended,
            "provider_cost_micros": provider_cost_micros,
            "billed_cost_micros": billed_cost_micros,
        }
