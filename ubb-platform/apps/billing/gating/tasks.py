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
    durable ledger for every enforcing tenant.

    Prepaid: per-wallet ``livebal`` MIN-merge toward the durable wallet balance
    (only lowers — credits are applied via the credit() hooks, so reconcile
    repairs drift-high / the bounded seed window, never re-raises a missed
    credit). Postpaid: per-OWNER ``livespend`` MAX-merge toward the
    owner-aggregated month-to-date billed total (raises to catch the first-use
    under-count). Iterates Wallet rows for prepaid (a wallet => a billing
    owner, so allocated seats are covered, not just account_type in/business).

    This pass IS the hourly patrol (#44, delivery spec §C — no new scheduled
    task): the per-owner reconcile drives missed signal transitions for both
    families and re-aligns the fast stop flag to durable truth; the
    tenant-level ``run_patrol`` leg then re-mints unannounced announcements,
    sweeps over-limit tasks into the kill flow, and records the outcome
    counters for the ops surface."""
    from apps.platform.tenants.models import Tenant
    from apps.platform.customers.models import Customer
    from apps.billing.wallets.models import Wallet
    from apps.billing.gating import patrol
    from apps.billing.gating.services.live_ledger_service import LiveLedgerService
    from apps.billing.gating.services.budget_service import _period
    from apps.metering.queries import get_customer_ids_with_usage

    for tenant in Tenant.objects.filter(enforcement_mode="enforcing"):
        flag_realigned = 0

        def _count(outcome):
            return 1 if outcome and outcome.get("flag_realigned") else 0

        try:
            if tenant.billing_mode == "postpaid":
                _label, start, end = _period()
                cust_ids = list(get_customer_ids_with_usage(tenant.id, start, end))
                owners = {c.resolve_billing_owner().id
                          for c in Customer.all_objects.filter(id__in=cust_ids)}
                # P6b deadlock fix: ALSO reconcile owners suspended for budget
                # that have NO current-month usage. A suspended owner is
                # start-gate-blocked, so it never appears in
                # get_customer_ids_with_usage — and reconcile_postpaid (its only
                # un-suspend path; credit() is a postpaid no-op) would never run,
                # stranding it suspended forever past month rollover.
                owners |= set(Customer.all_objects.filter(
                    tenant=tenant, status="suspended", suspension_reason="budget_exceeded"
                ).values_list("id", flat=True))
                for owner_id in owners:
                    flag_realigned += _count(
                        LiveLedgerService.reconcile_postpaid(owner_id, tenant))
            else:
                for owner_id in Wallet.objects.filter(
                        customer__tenant=tenant).values_list("customer_id", flat=True):
                    flag_realigned += _count(
                        LiveLedgerService.reconcile_prepaid(owner_id, tenant))
        except Exception:
            logger.exception("live_ledger.reconcile_tenant_failed",
                             extra={"data": {"tenant_id": str(tenant.id)}})
        try:
            patrol.run_patrol(tenant, flag_realigned=flag_realigned)
        except Exception:
            logger.exception("patrol.tenant_failed",
                             extra={"data": {"tenant_id": str(tenant.id)}})
