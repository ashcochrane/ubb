import logging
from decimal import Decimal

from django.db import transaction, IntegrityError
from django.db.models import F
from django.utils import timezone

from apps.billing.tenant_billing.models import TenantBillingPeriod

logger = logging.getLogger(__name__)


class TenantBillingService:
    @staticmethod
    def get_or_create_current_period(tenant):
        """Get or create the current month's open billing period for a tenant.

        Uses half-open interval [first_of_month, first_of_next_month).
        Uses timezone.now().date() for UTC-safe month boundaries.
        """
        today = timezone.now().date()
        first_of_month = today.replace(day=1)
        if today.month == 12:
            first_of_next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            first_of_next_month = today.replace(month=today.month + 1, day=1)

        try:
            period, _ = TenantBillingPeriod.objects.get_or_create(
                tenant=tenant,
                period_start=first_of_month,
                period_end=first_of_next_month,
                defaults={"status": "open"},
            )
        except IntegrityError:
            # Race condition: partial unique index rejected a second open period.
            # Another request won the create — fetch the existing one.
            period = TenantBillingPeriod.objects.get(
                tenant=tenant,
                period_start=first_of_month,
                period_end=first_of_next_month,
            )
        return period

    @staticmethod
    def accumulate_usage(tenant, billed_cost_micros):
        """Atomically increment the current billing period's usage totals.

        Called synchronously in the usage recording hot path. The atomic
        UPDATE is fast (no select, just increment) so this does not add
        meaningful latency.
        """
        period = TenantBillingService.get_or_create_current_period(tenant)
        rows = TenantBillingPeriod.objects.filter(id=period.id, status="open").update(
            total_usage_cost_micros=F("total_usage_cost_micros") + billed_cost_micros,
            event_count=F("event_count") + 1,
        )
        if rows == 0:
            # Period was closed between get_or_create and update — get fresh period and retry once
            logger.warning(
                "accumulate_usage: period closed mid-request, retrying with fresh period",
                extra={"data": {"tenant_id": str(tenant.id), "period_id": str(period.id)}},
            )
            period = TenantBillingService.get_or_create_current_period(tenant)
            rows = TenantBillingPeriod.objects.filter(id=period.id, status="open").update(
                total_usage_cost_micros=F("total_usage_cost_micros") + billed_cost_micros,
                event_count=F("event_count") + 1,
            )
            if rows == 0:
                logger.error(
                    "accumulate_usage: retry also updated zero rows",
                    extra={"data": {"tenant_id": str(tenant.id), "period_id": str(period.id)}},
                )

    @staticmethod
    def _calculate_fees(tenant, period):
        """Calculate fees per product using ProductFeeConfig.

        Falls back to legacy percentage if no ProductFeeConfig rows exist.
        """
        from apps.billing.tenant_billing.models import ProductFeeConfig

        total_fee = 0
        line_items = []

        configs = list(ProductFeeConfig.objects.filter(tenant=tenant))

        if configs:
            for config in configs:
                if config.fee_type == "flat":
                    fee = config.config.get("amount_micros", 0)
                elif config.fee_type == "percentage":
                    pct = Decimal(str(config.config.get("percentage", "0")))
                    fee = int(Decimal(period.total_usage_cost_micros) * pct / Decimal(100))
                    fee = (fee // 10_000) * 10_000  # Floor to cent boundary
                else:
                    continue

                total_fee += fee
                line_items.append({
                    "product": config.product,
                    "description": f"{config.product} fee ({config.fee_type})",
                    "amount_micros": fee,
                })
        else:
            # Legacy fallback: single percentage from billing config
            from apps.billing.queries import get_billing_config
            billing_config = get_billing_config(tenant.id)
            raw_fee = (
                Decimal(period.total_usage_cost_micros)
                * billing_config.platform_fee_percentage
                / Decimal(100)
            )
            fee = int(raw_fee)
            fee = (fee // 10_000) * 10_000
            total_fee = fee
            line_items.append({
                "product": "platform",
                "description": "Platform fee",
                "amount_micros": fee,
            })

        return total_fee, line_items

    @staticmethod
    def close_period(period):
        """Reconcile then close a billing period, calculating platform fee.

        Reconciliation runs outside the transaction to get accurate totals
        before locking and closing.
        """
        # Reconcile first — catches any accumulate_usage drift near month-end
        TenantBillingService.reconcile_period(period)

        with transaction.atomic():
            period = TenantBillingPeriod.objects.select_for_update().get(pk=period.pk)
            if period.status != "open":
                return

            fee_micros, line_items = TenantBillingService._calculate_fees(
                period.tenant, period
            )

            period.status = "closed"
            period.platform_fee_micros = fee_micros
            period.save(update_fields=["status", "platform_fee_micros", "updated_at"])

    @staticmethod
    def reconcile_period(period):
        """Recompute a billing period's totals from actual UsageEvent records.

        Used as a belt-and-suspenders reconciliation for any accumulate_usage
        failures. Safe to run on open or closed periods.

        Reads via metering query interface — no direct model import.
        """
        from apps.metering.queries import get_period_totals

        totals = get_period_totals(period.tenant_id, period.period_start, period.period_end)
        recomputed_cost = totals["total_cost_micros"]
        recomputed_count = totals["event_count"]

        # Skip if no events found — avoids zeroing out periods where events
        # were recorded via accumulate_usage but aren't queryable here.
        if recomputed_count == 0 and period.event_count > 0:
            return

        if (recomputed_cost != period.total_usage_cost_micros
                or recomputed_count != period.event_count):
            logger.warning(
                "Billing period reconciliation drift detected",
                extra={"data": {
                    "period_id": str(period.id),
                    "tenant": period.tenant.name,
                    "stored_cost": period.total_usage_cost_micros,
                    "recomputed_cost": recomputed_cost,
                    "stored_count": period.event_count,
                    "recomputed_count": recomputed_count,
                }},
            )
            TenantBillingPeriod.objects.filter(id=period.id).update(
                total_usage_cost_micros=recomputed_cost,
                event_count=recomputed_count,
            )
