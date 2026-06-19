"""Billing Query Interface — Cross-Product Read Contract.

This module provides the ONLY approved way for other products
(and the API layer) to read billing data. Functions return
model instances or scalars, never require callers to import
billing models directly.

If billing becomes a separate service, these functions become
HTTP calls. All callers remain untouched.

Consumers:
- apps/billing/gating/services/risk_service.py → get_billing_config(), get_customer_min_balance()
- apps/billing/handlers.py → get_customer_min_balance()
- apps/billing/stripe/services/stripe_service.py → get_billing_config()
- apps/billing/tenant_billing/services.py → get_billing_config()
- apps/metering/usage/services/usage_service.py → is_usage_period_closed()
"""


def get_billing_config(tenant_id):
    """Returns billing config for a tenant. Lazily creates with defaults if missing."""
    from apps.billing.tenant_billing.models import BillingTenantConfig

    config, _ = BillingTenantConfig.objects.get_or_create(tenant_id=tenant_id)
    return config


def get_customer_min_balance(customer_id, tenant_id):
    """Returns the effective min balance: customer override -> tenant default -> 0."""
    from apps.billing.wallets.models import CustomerBillingProfile

    try:
        profile = CustomerBillingProfile.objects.get(customer_id=customer_id)
        if profile.min_balance_micros is not None:
            return profile.min_balance_micros
    except CustomerBillingProfile.DoesNotExist:
        pass

    config = get_billing_config(tenant_id)
    return config.min_balance_micros


def get_customer_balance(customer_id):
    """Returns wallet balance, or 0 if no wallet exists."""
    from apps.billing.wallets.models import Wallet

    try:
        wallet = Wallet.objects.get(customer_id=customer_id)
        return wallet.balance_micros
    except Wallet.DoesNotExist:
        return 0


def record_live_usage_debit(owner_id, tenant, billed_cost_micros, *,
                            effective_at=None, now=None):
    """Tier-2 synchronous live-ledger hook — the cross-product PORT for the
    metering choke point.

    Maintains the billing owner's live spend/balance counter synchronously at
    record_usage time so the response can carry a real stop verdict (P3 reads
    it). Exposed here (the sanctioned billing read/port contract) so metering
    need not import a billing internal — mirrors is_usage_period_closed().
    No-op unless the tenant has enforcement enabled. Returns the live verdict
    dict ({mode, balance_micros|spend_micros, key}) or None.
    """
    from apps.billing.gating.services.live_ledger_service import LiveLedgerService
    return LiveLedgerService.record_usage_debit(
        owner_id, tenant, billed_cost_micros, effective_at=effective_at, now=now)


def is_usage_period_closed(owner_id, period_start) -> bool:
    """True when the billing owner's postpaid usage invoice for the calendar
    month starting at ``period_start`` (date) is FROZEN — i.e. matches the
    same predicate that destroys billability at push time.

    Frozen = status in (pushing, pushed, skipped, failed_permanent)
    OR push_phase != "" OR stripe_invoice_id != "" OR line_snapshot != [].
    The line_snapshot check is the load-bearing one: under the F0.1 resume
    semantics the lines are frozen at FIRST CLAIM (Phase 1), so a
    ``status="failed"`` row whose Phase 2 died before Invoice.create — and a
    reclaimed ``pending`` row — both carry a frozen snapshot while reading as
    "untouched" on status/phase/pointer alone. Accepting a backfill into such
    a period would commit an event the frozen lines permanently exclude:
    recorded but never billed. A genuinely-fresh ``pending`` row (empty
    snapshot, no phase, no pointer) re-aggregates safely and does NOT close
    the period. No row at all = open.
    """
    from django.db.models import Q
    from apps.billing.invoicing.models import CustomerUsageInvoice

    return CustomerUsageInvoice.objects.filter(
        customer_id=owner_id, period_start=period_start,
    ).filter(
        Q(status__in=("pushing", "pushed", "skipped", "failed_permanent"))
        | ~Q(push_phase="") | ~Q(stripe_invoice_id="") | ~Q(line_snapshot=[])
    ).exists()
