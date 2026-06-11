import logging

from celery import shared_task

logger = logging.getLogger("ubb.billing")


@shared_task(queue="ubb_billing")
def reconcile_budget_counters():
    """Rebuild per-customer budget counters from the durable ledger (drift correction)."""
    from apps.platform.customers.models import Customer
    from apps.billing.gating.models import BudgetConfig
    from apps.billing.gating.services.budget_service import BudgetService, _period
    from apps.metering.queries import get_customer_ids_with_usage

    _label, start, end = _period()
    ids = set(BudgetConfig.objects.filter(customer__isnull=False, cap_micros__gt=0)
              .values_list("customer_id", flat=True))
    default_tenants = list(BudgetConfig.objects.filter(customer__isnull=True, cap_micros__gt=0)
                           .values_list("tenant_id", flat=True))
    if default_tenants:
        ids |= set(get_customer_ids_with_usage(default_tenants, start, end))
    for customer in Customer.objects.filter(id__in=ids):
        try:
            BudgetService.reconcile_customer(customer)
        except Exception:
            logger.exception("budget.reconcile_failed", extra={"data": {"customer_id": str(customer.id)}})
