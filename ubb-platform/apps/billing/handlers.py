import logging

from apps.platform.events.schemas import CustomerDeleted, UsageRecorded
from apps.platform.tenants.models import Tenant
from apps.billing.tenant_billing.services import TenantBillingService

logger = logging.getLogger("ubb.events")


def handle_usage_recorded_billing(event_id, payload):
    """Outbox handler: draw the usage down against the owner's wallet.

    Registered as outbox handler with requires_product="billing".
    Called by the outbox dispatcher with (event_id, payload) signature.

    The wallet movement and its whole winning-branch tail — exactly-once
    debit, lot consumption, BalanceOverage on zero-cross, the #39/#40
    floor-crossing lanes (or the Tier-1 suspension when enforcement is off),
    and BalanceLow under the auto-top-up trigger — live behind the wallet
    seam (``wallet_ops.draw_down_usage``, #109). This handler keeps what is
    caller-side by decision 7: the postpaid branch, the owner resolution,
    billing-period accumulation, and the budget counters.

    This handler NEVER calls Stripe or dispatches payment tasks.
    Payment connectors subscribe to the emitted events.
    """
    evt = UsageRecorded.from_payload(payload)
    tenant = Tenant.objects.get(id=evt.tenant_id)
    billed_cost_micros = evt.cost_micros

    if billed_cost_micros > 0:
        from apps.platform.customers.models import Customer
        seat = Customer.objects.get(id=evt.customer_id)
        # Postpaid has no wallet to draw down, and (#39) its budget-cap
        # stop/suspension rides the StopSignalState transition guard from the
        # fast lane at the crossing plus the hourly reconcile's SET power —
        # this handler no longer reads the stop flag (the old D13 shape), so
        # floor-stop and suspension cannot double-fire.
        if tenant.billing_mode != "postpaid":
            from apps.billing.wallets import operations as wallet_ops

            owner_id = evt.billing_owner_id or str(seat.resolve_billing_owner().id)
            usage_event_id = evt.event_id
            # The whole drawdown — lock, lazy expiry, exactly-once debit, lot
            # consumption, and the winning-branch tail (BalanceOverage, the
            # #39/#40 crossing lanes or the Tier-1 suspension, BalanceLow) —
            # lives behind the wallet seam (#109).
            wallet_ops.draw_down_usage(
                customer_id=owner_id, tenant=tenant,
                usage_event_id=usage_event_id,
                billed_cost_micros=billed_cost_micros)

        # Shared tail — control + attribution stay on the SEAT:
        TenantBillingService.accumulate_usage(tenant, billed_cost_micros)
        # Budget policy: budgets are EFFECTIVE-month basis; the live Redis
        # counter tracks the CURRENT wall-clock month only. A backdated event
        # whose effective month is a PRIOR month must NOT inflate this month's
        # counter (the hourly reconcile_budget_counters rebuild — already
        # effective_at-filtered via get_customer_cost_totals — is the source
        # of truth). Absent/unparseable effective_at = legacy payload =
        # current behavior (increment).
        # Documented enforcement bypass: an enforcing-capped seat can backdate
        # usage into the prior month to evade the live cap. The exposure is
        # bounded by Tenant.backfill_window_days (0..60); tenants needing
        # airtight caps set it low — 0 disables backfill entirely.
        from django.utils import timezone as _tz
        from django.utils.dateparse import parse_datetime
        from apps.billing.gating.crossing import same_month
        count_in_live = True
        raw_eff = evt.effective_at
        if raw_eff:
            eff = parse_datetime(raw_eff)
            if eff is not None:
                count_in_live = same_month(eff, _tz.now())
        if count_in_live:
            from apps.billing.gating.services.budget_service import BudgetService
            BudgetService.record_usage_spend(seat, billed_cost_micros)


def handle_customer_deleted_billing(event_id, payload):
    """Outbox handler: clean up billing resources when customer is deleted.

    Registered as outbox handler with requires_product="billing".
    Soft-deletes Wallet and AutoTopUpConfig for the customer.
    """
    customer_id = CustomerDeleted.from_payload(payload).customer_id

    from apps.billing.wallets.models import Wallet
    from apps.billing.topups.models import AutoTopUpConfig

    try:
        Wallet.objects.get(customer_id=customer_id).soft_delete()
    except Wallet.DoesNotExist:
        pass
    try:
        AutoTopUpConfig.objects.get(customer_id=customer_id).soft_delete()
    except AutoTopUpConfig.DoesNotExist:
        pass
