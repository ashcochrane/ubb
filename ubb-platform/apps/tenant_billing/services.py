import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.tenant_billing.models import TenantBillingPeriod

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

        period, _ = TenantBillingPeriod.objects.get_or_create(
            tenant=tenant,
            period_start=first_of_month,
            period_end=first_of_next_month,
            defaults={"status": "open"},
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
        TenantBillingPeriod.objects.filter(id=period.id, status="open").update(
            total_usage_cost_micros=F("total_usage_cost_micros") + billed_cost_micros,
            event_count=F("event_count") + 1,
        )

    @staticmethod
    @transaction.atomic
    def close_period(period):
        """Close a billing period and calculate platform fee using Decimal arithmetic."""
        period = TenantBillingPeriod.objects.select_for_update().get(pk=period.pk)
        if period.status != "open":
            return

        # Use Decimal arithmetic — no float conversion
        fee_micros = int(
            period.total_usage_cost_micros
            * period.tenant.platform_fee_percentage
            / Decimal(100)
        )

        period.status = "closed"
        period.platform_fee_micros = fee_micros
        period.save(update_fields=["status", "platform_fee_micros", "updated_at"])
