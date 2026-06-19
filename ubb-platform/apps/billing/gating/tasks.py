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


@shared_task(queue="ubb_billing")
def reconcile_live_ledgers():
    """Tier-2 (P2/WS1): MIN/MAX-merge the synchronous live counters toward the
    durable ledger for every enforcement-enabled tenant (enforcement_mode != off).

    Prepaid: per-wallet ``livebal`` MIN-merge toward the durable wallet balance
    (only lowers — credits are applied via the credit() hooks, so reconcile
    repairs drift-high / the bounded seed window, never re-raises a missed
    credit). Postpaid: per-OWNER ``livespend`` MAX-merge toward the
    owner-aggregated month-to-date billed total (raises to catch the first-use
    under-count). Iterates Wallet rows for prepaid (a wallet => a billing
    owner, so allocated seats are covered, not just account_type in/business)."""
    from apps.platform.tenants.models import Tenant
    from apps.platform.customers.models import Customer
    from apps.billing.wallets.models import Wallet
    from apps.billing.gating.services.live_ledger_service import LiveLedgerService
    from apps.billing.gating.services.budget_service import _period
    from apps.metering.queries import get_customer_ids_with_usage

    for tenant in Tenant.objects.exclude(enforcement_mode="off"):
        try:
            if tenant.billing_mode == "postpaid":
                _label, start, end = _period()
                cust_ids = list(get_customer_ids_with_usage(tenant.id, start, end))
                owners = {c.resolve_billing_owner().id
                          for c in Customer.all_objects.filter(id__in=cust_ids)}
                for owner_id in owners:
                    LiveLedgerService.reconcile_postpaid(owner_id, tenant)
            else:
                for owner_id in Wallet.objects.filter(
                        customer__tenant=tenant).values_list("customer_id", flat=True):
                    LiveLedgerService.reconcile_prepaid(owner_id, tenant)
        except Exception:
            logger.exception("live_ledger.reconcile_tenant_failed",
                             extra={"data": {"tenant_id": str(tenant.id)}})
