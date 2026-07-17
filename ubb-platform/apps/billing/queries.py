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


def get_customer_soft_min_balance(customer_id, tenant_id):
    """Returns the effective SOFT floor value (#40, spec §F), or None = no
    soft floor. Same orientation as get_customer_min_balance: the wind-down
    line is -value (negative values place it above zero). Resolution mirrors
    the hard floor's — customer override -> tenant default -> None — then
    clamps so the soft line sits AT OR ABOVE the hard floor's line
    (value <= the hard's value): the set-time API validation can go stale
    across levels (a customer override vs a later-changed tenant hard
    default), so the resolver, not the writer, guarantees the invariant.
    """
    from apps.billing.wallets.models import CustomerBillingProfile

    soft = None
    try:
        profile = CustomerBillingProfile.objects.get(customer_id=customer_id)
        soft = profile.soft_min_balance_micros
    except CustomerBillingProfile.DoesNotExist:
        pass
    if soft is None:
        soft = get_billing_config(tenant_id).soft_min_balance_micros
    if soft is None:
        return None
    return min(soft, get_customer_min_balance(customer_id, tenant_id))


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


def read_live_stop(owner_id, tenant) -> dict:
    """Read the customer-wide stop verdict for a billing owner — the
    cross-product port for the metering replay paths. Returns
    {stop, stop_reason, stop_scope}; {stop: False, ...} when enforcement is off
    (short-circuits before touching Redis)."""
    from apps.billing.gating.services.live_ledger_service import LiveLedgerService
    return LiveLedgerService.read_stop(owner_id, tenant)


def get_negative_balance_stats(tenant_id=None):
    """Aged-negatives ops metric (#41, pin 10) — the cross-product read for
    the ops/ingest-health surface. Counts wallets currently below zero and
    the age of the oldest, from Wallet.negative_since (the ≥0 → <0 transition
    stamp; soft-deleted wallets excluded by the default manager). Visibility
    only: no reminder events, no auto-close — collections stay between the
    tenant, their customer, and Stripe."""
    from django.db.models import Min
    from django.utils import timezone
    from apps.billing.wallets.models import Wallet
    qs = Wallet.objects.filter(negative_since__isnull=False)
    if tenant_id is not None:
        qs = qs.filter(customer__tenant_id=tenant_id)
    oldest = qs.aggregate(oldest=Min("negative_since"))["oldest"]
    return {
        "negative_balance_count": qs.count(),
        "oldest_negative_age_seconds": (
            (timezone.now() - oldest).total_seconds() if oldest else 0.0),
    }


def get_patrol_stats(tenant_id=None):
    """Patrol-outcome counters for the ops/ingest-health surface (#44,
    delivery spec §F) — trailing 7 days of day-bucketed ``PatrolOutcome``
    rows, summed per outcome. Visibility only: a nonzero count means the
    patrol actually healed a crash/blind-window corner (re-minted a lost
    announcement, re-aligned an orphaned stop flag, swept a crashed kill,
    repaired a wedged live balance — count, micros, lapsed candidates; #45);
    a persistent spike means a lane is unhealthy."""
    from datetime import timedelta
    from django.db.models import Sum
    from django.utils import timezone
    from apps.billing.gating import patrol
    from apps.billing.gating.models import PatrolOutcome
    since = timezone.now().date() - timedelta(days=7)
    qs = PatrolOutcome.objects.filter(day__gte=since)
    if tenant_id is not None:
        qs = qs.filter(tenant_id=tenant_id)
    agg = dict(qs.values_list("outcome").annotate(n=Sum("count")))
    return {f"patrol_{outcome}_7d": int(agg.get(outcome, 0))
            for outcome in (patrol.OUTCOME_REMINTED,
                            patrol.OUTCOME_FLAG_REALIGNED,
                            patrol.OUTCOME_SWEEP_KILLED,
                            patrol.OUTCOME_REPAIRED,
                            patrol.OUTCOME_REPAIRED_MICROS,
                            patrol.OUTCOME_REPAIR_LAPSED)}


def get_stop_signal_state(owner_id, tenant_id, family="floor_stop"):
    """Plain-data snapshot of the owner's DURABLE stop-signal ledger row for
    one family (#41 stop-context tagging) — the cross-product read for the
    metering record/settle paths. Returns
    {state, episode_seq, reason, transitioned_at} or None when the family has
    never transitioned for this owner. One indexed point read (unique on
    (owner, family)); the caller decides what an open episode means."""
    from apps.billing.gating.models import StopSignalState
    return (StopSignalState.objects
            .filter(owner_id=owner_id, tenant_id=tenant_id, family=family)
            .values("state", "episode_seq", "reason", "transitioned_at")
            .first())


def acquire_ingest_holds(owner_id, tenant, items):
    """Accept-time atomic estimate-hold for the async ingest path (Task 4) —
    the cross-product PORT for the metering ingest choke point.

    items: [{"estimate_micros": int, "effective_at": datetime|None}]

    effective_at (optional, default None == current month) gates the I9
    postpaid prior-month guard in HoldService.acquire (a backdated item's
    livespend move is skipped).

    One-rule (#37): the acquire ALWAYS holds, against the wallet only — no
    item is ever rejected (the accept-time unit-cap lane is retired; task
    limits are detected at settle with exact provider costs). Returns one
    verdict dict per item, same order as `items`: {"held": True,
    "stop": bool, "stop_reason": str|None, "stop_scope": str|None}. No-op
    passthrough (every item held, unstopped) when the tenant's
    enforcement_mode is off. NEVER raises — fails open on any Redis error
    (the durable start-gate remains the backstop), mirroring
    record_live_usage_debit.
    """
    from apps.billing.gating.services.hold_service import HoldService
    return HoldService.acquire(owner_id, tenant, items)


def settle_ingest_hold(owner_id, tenant, delta_micros, *, effective_at=None):
    """Settle a prior estimate hold once the actual billed cost is known
    (Task 6) — cross-product port. delta_micros = estimate − exact: positive
    credits back the over-hold, negative debits further. Routes through
    HoldService.settle -> LiveLedgerService.credit (the same MIN-merge-safe
    site every other credit hook uses). Never raises.

    effective_at (optional, default None == current month): forwards to
    HoldService.settle's prior-month guard — a POSTPAID event backdated to a
    prior calendar month skips the livespend adjustment (I9 parity; its
    matching acquire() already skipped the hold-time move). Omitting it
    preserves every pre-existing caller's behavior exactly."""
    from apps.billing.gating.services.hold_service import HoldService
    HoldService.settle(owner_id, tenant, delta_micros, effective_at=effective_at)


def release_ingest_hold(owner_id, tenant, estimate_micros, *, effective_at=None):
    """Fully release (credit back) a prior estimate hold — duplicate
    ingest, failed append, or any path that must undo acquire() entirely.
    Cross-product port; equivalent to
    settle_ingest_hold(delta_micros=estimate_micros). Never raises.
    effective_at forwards to the same prior-month guard as
    settle_ingest_hold (optional, default None == current month)."""
    from apps.billing.gating.services.hold_service import HoldService
    HoldService.release(owner_id, tenant, estimate_micros, effective_at=effective_at)


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
