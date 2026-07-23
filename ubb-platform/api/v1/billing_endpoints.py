from datetime import date
from uuid import UUID

from ninja import Router

from api.v1.pagination import empty_page, page
from api.v1.topups import start_top_up
from api.v1.schemas import (
    PreCheckRequest, PreCheckResponse,
    BalanceResponse,
    ConfigureAutoTopUpRequest,
    CreateTopUpRequest,
    WithdrawRequest,
    RefundRequest,
    DebitRequest, CreditRequest, DebitCreditResponse,
    TopUpCheckoutResponse, WithdrawResponse, RefundResponse,
    PaginatedWalletTransactions,
    CreateGrantRequest, GrantOut, PaginatedGrants,
    RevenueAnalyticsResponse,
    BudgetConfigIn, BudgetConfigOut, BudgetStatusOut,
    CustomerBillingProfileIn, CustomerBillingProfileOut,
    UsageInvoiceListResponse, PostpaidConfigIn, PostpaidConfigOut,
    TenantUsageInvoiceListResponse,
    grant_out, tenant_usage_invoice_out, usage_invoice_out,
    wallet_transaction_out,
)
from core.auth import ADMIN, ApiKeyAuth, ProductAccess, READ, WRITE, role_floor
from core.identifiers import UUIDIdentifier
from core.problems import Problem, ProblemOut
from core.responses import StatusResponse
from core.time_windows import REPORT_WINDOW_MAX_DAYS
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
from apps.platform.customers.models import Customer
from apps.billing.topups.models import AutoTopUpConfig
from apps.billing.gating.services.risk_service import RiskService
from apps.billing.connectors.stripe.stripe_api import create_checkout_session
from django.db import transaction
from django.shortcuts import get_object_or_404

billing_router = Router(auth=ApiKeyAuth())

_product_check = ProductAccess("billing")


# ---------- Customer billing endpoints ----------


@billing_router.get("/customers/{customer_id}/balance", response=BalanceResponse)
@role_floor(READ)
def get_balance(request, customer_id: UUIDIdentifier):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    from apps.billing.wallets import operations as wallet_ops
    from apps.billing.wallets.models import Wallet
    try:
        wallet = Wallet.objects.get(customer=customer)
        return {"balance_micros": wallet.balance_micros, "currency": wallet.currency,
                # #41 pin 10: since when the balance has been negative
                # (null when ≥ 0). Visibility only — nothing acts on it.
                "negative_since": (wallet.negative_since.isoformat()
                                   if wallet.negative_since else None),
                **wallet_ops.balance_summary(wallet)}
    except Wallet.DoesNotExist:
        # CUR-1: no-wallet fallback reports the tenant currency, not a literal USD.
        return {"balance_micros": 0,
                "currency": (request.auth.tenant.default_currency or "usd").lower(),
                "promo_micros": 0, "expiring_micros": 0, "next_expiry_at": None,
                "negative_since": None}


@billing_router.post("/debit", response=DebitCreditResponse)
@role_floor(ADMIN)
@records_audit("wallet.debited")
def debit(request, payload: DebitRequest):
    _product_check(request)
    from apps.billing.wallets import operations as wallet_ops

    customer = get_object_or_404(
        Customer, external_id=payload.customer_id, tenant=request.auth.tenant
    )

    # Co-commit pattern (#109 decision 8): the outer atomic makes the ADR-004
    # audit row land in the same transaction as the money movement.
    with transaction.atomic():
        result = wallet_ops.debit(
            customer_id=customer.id, tenant=request.auth.tenant,
            amount_micros=payload.amount_micros,
            idempotency_key=payload.idempotency_key,
            allow_negative=payload.allow_negative,
            audit=wallet_ops.Audit(actor=payload.actor,
                                   reason_code=payload.reason_code,
                                   reference=payload.reference))
        if result.outcome == "applied":
            # An idempotent replay skips this, so it fires once per real debit.
            audit_record(
                action="wallet.debited", tenant_id=request.auth.tenant.id,
                resource_type="wallet", resource_id=customer.id,
                metadata={"customer_id": payload.customer_id,
                          "amount_micros": payload.amount_micros,
                          "reason_code": payload.reason_code,
                          "reference": payload.reference,
                          "transaction_id": result.transaction_id})
    # Raised OUTSIDE the atomic: the refusal's lazy-expiry side effects commit
    # (decision 3) and the body quotes the post-expiry balance.
    if result.outcome == "refused":
        raise Problem(
            "would_overdraw",
            "debit would breach the overdraft floor; "
            "pass allow_negative=true to force",
            extensions={"floor_micros": result.floor_micros,
                        "balance_micros": result.balance_micros})

    return {"new_balance_micros": result.balance_micros,
            "transaction_id": result.transaction_id}


@billing_router.post("/credit", response=DebitCreditResponse)
@role_floor(ADMIN)
@records_audit("wallet.credited")
def credit(request, payload: CreditRequest):
    """Credit the wallet with LEGACY BASE money (non-expiring, no grant lot).

    Deliberately untouched by F4.3: base is derived (balance minus active
    grant remainders), so an ADJUSTMENT credit simply grows base. Tenants who
    want expiring or promo credit use POST /customers/{id}/grants instead.
    """
    _product_check(request)
    from apps.billing.wallets import operations as wallet_ops

    customer = get_object_or_404(
        Customer, external_id=payload.customer_id, tenant=request.auth.tenant
    )

    with transaction.atomic():  # co-commit: audit rides the money transaction
        result = wallet_ops.credit(
            customer_id=customer.id, tenant=request.auth.tenant,
            amount_micros=payload.amount_micros,
            idempotency_key=payload.idempotency_key,
            audit=wallet_ops.Audit(actor=payload.actor,
                                   reason_code=payload.reason_code,
                                   reference=payload.reference,
                                   description=f"Credit: {payload.source}"))
        if result.outcome == "applied":
            # Audit the hand-moved credit (an idempotent replay skips this).
            audit_record(
                action="wallet.credited", tenant_id=request.auth.tenant.id,
                resource_type="wallet", resource_id=customer.id,
                metadata={"customer_id": payload.customer_id,
                          "amount_micros": payload.amount_micros,
                          "source": payload.source,
                          "reason_code": payload.reason_code,
                          "transaction_id": result.transaction_id})

    return {"new_balance_micros": result.balance_micros,
            "transaction_id": result.transaction_id}


@billing_router.put("/customers/{customer_id}/auto-top-up", response=StatusResponse)
@role_floor(ADMIN)
@records_audit("auto_top_up.configured")
def configure_auto_top_up(request, customer_id: UUIDIdentifier, payload: ConfigureAutoTopUpRequest):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    with transaction.atomic():
        AutoTopUpConfig.objects.update_or_create(
            customer=customer,
            defaults={
                "is_enabled": payload.is_enabled,
                "trigger_threshold_micros": payload.trigger_threshold_micros,
                "top_up_amount_micros": payload.top_up_amount_micros,
            },
        )
        audit_record(
            action="auto_top_up.configured", tenant_id=request.auth.tenant.id,
            resource_type="auto_top_up", resource_id=customer.id,
            metadata={"customer_id": str(customer.id),
                      "is_enabled": payload.is_enabled,
                      "trigger_threshold_micros": payload.trigger_threshold_micros,
                      "top_up_amount_micros": payload.top_up_amount_micros})
    return {"status": "ok"}


@billing_router.post("/customers/{customer_id}/top-up", response=TopUpCheckoutResponse)
@role_floor(WRITE)
@records_audit("top_up.requested")
def create_top_up(request, customer_id: UUIDIdentifier, payload: CreateTopUpRequest):
    """Start a top-up. Replay-safe: idempotency_key is required and unique
    per customer — a retried call re-uses the original attempt and never
    starts a second charge."""
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    return start_top_up(request, customer, request.auth.tenant, payload,
                        trigger="manual", checkout=create_checkout_session)


@billing_router.post("/customers/{customer_id}/withdraw", response=WithdrawResponse)
@role_floor(ADMIN)
@records_audit("wallet.withdrawn")
def withdraw(request, customer_id: UUIDIdentifier, payload: WithdrawRequest):
    """Withdraw base + paid money. Promo credit is NOT withdrawable (F4.3):
    availability is balance minus active promo remainders."""
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    from apps.billing.wallets import operations as wallet_ops

    with transaction.atomic():  # co-commit: audit rides the money transaction
        result = wallet_ops.withdraw(
            customer_id=customer.id, tenant=request.auth.tenant,
            amount_micros=payload.amount_micros,
            idempotency_key=payload.idempotency_key,
            audit=wallet_ops.Audit(description=payload.description))
        if result.outcome == "applied":
            # Audit the hand-moved withdrawal (an idempotent replay skips this).
            audit_record(
                action="wallet.withdrawn", tenant_id=request.auth.tenant.id,
                resource_type="wallet", resource_id=customer.id,
                metadata={"customer_id": str(customer.id),
                          "amount_micros": payload.amount_micros,
                          "transaction_id": result.transaction_id})
    # Raised OUTSIDE the atomic: the refusal's lazy-expiry side effects commit
    # (decision 3) and the body quotes the post-expiry balance.
    if result.outcome == "refused":
        raise Problem(
            "insufficient_balance",
            "withdrawable balance (balance minus active promo credit) "
            "is below the requested amount",
            extensions={"balance_micros": result.balance_micros})

    return {"transaction_id": result.transaction_id,
            "balance_micros": result.balance_micros}


@billing_router.post("/pre-check", response=PreCheckResponse)
@role_floor(WRITE)
def pre_check(request, payload: PreCheckRequest):
    _product_check(request)
    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)
    result = RiskService.check(
        customer,
        create_task=payload.start_task,
        task_metadata=payload.task_metadata,
        external_task_id=payload.external_task_id,
        provider_cost_limit_micros=payload.provider_cost_limit_micros,
        parent_task_id=payload.parent_task_id,
    )
    return result


@billing_router.post("/customers/{customer_id}/refund", response=RefundResponse)
@role_floor(ADMIN)
@records_audit("usage.refunded")
def refund_usage(request, customer_id: UUIDIdentifier, payload: RefundRequest):
    """Refund a usage charge. LOT-AWARE (F4.3): the slices of the original
    USAGE_DEDUCTION that were funded by still-live grant lots are re-funded
    back into those lots (promo refunds restore the promo lot — they never
    become withdrawable cash); only the base-funded remainder, plus shares
    from since-expired/voided lots, lands as base credit."""
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    from apps.billing.wallets import operations as wallet_ops

    with transaction.atomic():  # co-commit: audit rides the money transaction
        result = wallet_ops.refund_usage(
            customer_id=customer.id, tenant=request.auth.tenant,
            usage_event_id=payload.usage_event_id,
            idempotency_key=payload.idempotency_key,
            reason=payload.reason)
        if result.outcome == "applied":
            # Audit the hand-moved refund (an idempotent replay skips this).
            audit_record(
                action="usage.refunded", tenant_id=request.auth.tenant.id,
                resource_type="wallet", resource_id=customer.id,
                metadata={"customer_id": str(customer.id),
                          "usage_event_id": str(payload.usage_event_id),
                          "refund_amount_micros": result.amount_micros,
                          "reason": payload.reason,
                          "transaction_id": result.transaction_id})
    # Raised OUTSIDE the atomic: any lazy-expiry side effects commit.
    if result.outcome == "refused":
        raise Problem("not_found", "usage event not found")
    if result.outcome == "replayed":
        # Replay quirk (preserved at the seam): the stored row's reference —
        # the usage event id — answers as the refund id.
        return {"refund_id": result.reference_id,
                "balance_micros": result.balance_micros}

    return {"refund_id": result.transaction_id,
            "balance_micros": result.balance_micros}


@billing_router.get("/customers/{customer_id}/transactions",
                    response=PaginatedWalletTransactions)
@role_floor(READ)
def get_transactions(request, customer_id: UUIDIdentifier, cursor: str = None, limit: int = 50):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)

    from apps.billing.wallets.models import Wallet
    try:
        wallet = Wallet.objects.get(customer=customer)
    except Wallet.DoesNotExist:
        return empty_page()

    return page(wallet.transactions.all(), cursor, limit,
                serialize=wallet_transaction_out)


# ---------- Credit grants (F4.3) ----------


@billing_router.post("/customers/{customer_id}/grants", response=GrantOut)
@role_floor(ADMIN)
@records_audit("grant.created")
def create_grant(request, customer_id: UUID, payload: CreateGrantRequest):
    """Create an expiring (or non-expiring) credit grant lot on the billing
    owner's wallet. Exactly-once via grant:{idempotency_key} — the GRANT
    WalletTransaction and the CreditGrant share one savepoint."""
    _product_check(request)
    from datetime import timedelta
    from django.utils import timezone
    from apps.billing.wallets import operations as wallet_ops

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    if payload.expires_at is not None and payload.expires_in_days is not None:
        raise Problem(
            "validation_error", "Pass expires_at OR expires_in_days, not both")
    if payload.expires_at is not None:
        if payload.expires_at.tzinfo is None:
            raise Problem("validation_error", "expires_at must be timezone-aware")
        if payload.expires_at <= timezone.now():
            raise Problem("validation_error", "expires_at must be in the future")
        expires_at = payload.expires_at
    elif payload.expires_in_days is not None:
        expires_at = timezone.now() + timedelta(days=payload.expires_in_days)
    else:
        expires_at = None  # non-expiring lot

    owner = customer.resolve_billing_owner()
    with transaction.atomic():  # co-commit: audit rides the money transaction
        result = wallet_ops.mint_grant(
            customer_id=owner.id, tenant=request.auth.tenant,
            kind=payload.kind, amount_micros=payload.amount_micros,
            expires_at=expires_at, idempotency_key=payload.idempotency_key,
            audit=wallet_ops.Audit(description=payload.description))
        if result.outcome == "applied":
            # Audit the new grant lot (an idempotent replay skips this).
            audit_record(
                action="grant.created", tenant_id=request.auth.tenant.id,
                resource_type="grant", resource_id=result.grant.id,
                metadata={"customer_id": str(customer.id),
                          "owner_id": str(owner.id),
                          "grant_id": str(result.grant.id),
                          "amount_micros": payload.amount_micros,
                          "kind": payload.kind,
                          "expires_at": (expires_at.isoformat()
                                         if expires_at else None),
                          "transaction_id": result.transaction_id})
    if result.outcome == "refused":
        raise Problem(
            "conflict", "idempotency_key already used by a non-grant transaction")
    return grant_out(result.grant, balance_micros=result.balance_micros,
                     transaction_id=result.transaction_id)


@billing_router.get("/customers/{customer_id}/grants", response=PaginatedGrants)
@role_floor(READ)
def list_grants(request, customer_id: UUID, status: str = None,
                cursor: str = None, limit: int = 50):
    """List the billing owner's grant lots (newest first), optional status filter."""
    _product_check(request)
    from apps.billing.wallets.models import CreditGrant, Wallet

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    owner = customer.resolve_billing_owner()
    wallet = Wallet.objects.filter(customer=owner).first()
    if wallet is None:
        return empty_page()

    qs = CreditGrant.objects.filter(wallet=wallet)
    if status:
        qs = qs.filter(status=status)

    return page(qs, cursor, limit, serialize=grant_out)


@billing_router.post("/customers/{customer_id}/grants/{grant_id}/void", response=GrantOut)
@role_floor(ADMIN)
@records_audit("grant.voided")
def void_grant(request, customer_id: UUID, grant_id: UUID):
    """Void a grant: debit its remaining (clamped so the balance never goes
    negative, like expiry) and retire the lot. Exactly-once via
    grant_void:{grant_id}; replays return the voided lot unchanged."""
    _product_check(request)
    from django.http import Http404
    from apps.billing.wallets import operations as wallet_ops

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    owner = customer.resolve_billing_owner()
    with transaction.atomic():  # co-commit: audit rides the money transaction
        result = wallet_ops.void_grant(
            customer_id=owner.id, tenant=request.auth.tenant, grant_id=grant_id)
        if result.outcome == "applied":
            # Audit the real void — replay / already-voided paths skip this.
            audit_record(
                action="grant.voided", tenant_id=request.auth.tenant.id,
                resource_type="grant", resource_id=result.grant.id,
                metadata={"customer_id": str(customer.id),
                          "grant_id": str(result.grant.id),
                          "kind": result.grant.kind,
                          "debited_micros": -result.amount_micros,
                          "transaction_id": result.transaction_id})
    if result.outcome == "refused":  # grant_not_found — the pre-seam 404
        raise Http404("No CreditGrant matches the given query.")
    return grant_out(result.grant, balance_micros=result.balance_micros,
                     transaction_id=result.transaction_id)


# ---------- Tenant billing endpoints ----------
# The tenant's own platform-fee billing periods and invoices live on the
# canonical `tenant/` mount (GET /api/v1/tenant/billing-periods, .../invoices).
# The billing-mount duplicates that once shadowed them were removed in the
# Stage-5 final sweep (#86): these resources exist for every tenant regardless
# of billing_mode, so the tenant mount — which does not gate on the billing
# product — is their one home. Only the customer-scoped usage invoices below
# are billing-product surface.


# ---------- Analytics ----------


@billing_router.get("/analytics/revenue", response=RevenueAnalyticsResponse)
@role_floor(READ)
def revenue_analytics(request, start_date: date = None, end_date: date = None):
    _product_check(request)
    from apps.metering.queries import get_revenue_analytics
    # #78: computed reports are cursor-exempt but parameter-bounded.
    if start_date and end_date:
        if end_date < start_date:
            raise Problem("validation_error", "end_date must not precede start_date")
        if (end_date - start_date).days > REPORT_WINDOW_MAX_DAYS:
            raise Problem("validation_error", "date window must not exceed 366 days")
    return get_revenue_analytics(request.auth.tenant.id, start_date, end_date)


# ---------- Budget config + status ----------


def _budget_out(cfg):
    return {"cap_micros": cfg.cap_micros, "enforce_mode": cfg.enforce_mode,
            "hard_stop_pct": cfg.hard_stop_pct, "alert_levels": cfg.alert_levels,
            "fail_closed": cfg.fail_closed}


def _upsert_budget(tenant, customer, payload):
    from apps.billing.gating.models import BudgetConfig, default_alert_levels
    cfg, _ = BudgetConfig.objects.update_or_create(
        tenant=tenant, customer=customer,
        defaults={"cap_micros": payload.cap_micros, "enforce_mode": payload.enforce_mode,
                  "hard_stop_pct": payload.hard_stop_pct,
                  "alert_levels": payload.alert_levels or default_alert_levels(),
                  "fail_closed": payload.fail_closed})
    return cfg


@billing_router.get("/budget", response=BudgetConfigOut)
@role_floor(READ)
def get_tenant_budget(request):
    _product_check(request)
    from apps.billing.gating.models import BudgetConfig
    cfg = BudgetConfig.objects.filter(tenant=request.auth.tenant, customer__isnull=True).first()
    if not cfg:
        return {"cap_micros": 0, "enforce_mode": "advisory", "hard_stop_pct": 100,
                "alert_levels": [50, 80, 100, 110], "fail_closed": False}
    return _budget_out(cfg)


@billing_router.put("/budget", response=BudgetConfigOut)
@role_floor(ADMIN)
@records_audit("budget.set")
def put_tenant_budget(request, payload: BudgetConfigIn):
    _product_check(request)
    with transaction.atomic():
        cfg = _upsert_budget(request.auth.tenant, None, payload)
        audit_record(
            action="budget.set", tenant_id=request.auth.tenant.id,
            resource_type="budget", resource_id=request.auth.tenant.id,
            metadata={"scope": "tenant", "cap_micros": cfg.cap_micros,
                      "enforce_mode": cfg.enforce_mode,
                      "hard_stop_pct": cfg.hard_stop_pct})
    return _budget_out(cfg)


@billing_router.get("/customers/{customer_id}/budget", response=BudgetConfigOut)
@role_floor(READ)
def get_customer_budget(request, customer_id: UUID):
    _product_check(request)
    from apps.billing.gating.models import BudgetConfig
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    cfg = BudgetConfig.objects.filter(tenant=request.auth.tenant, customer=customer).first()
    if not cfg:
        return {"cap_micros": 0, "enforce_mode": "advisory", "hard_stop_pct": 100,
                "alert_levels": [50, 80, 100, 110], "fail_closed": False}
    return _budget_out(cfg)


@billing_router.put("/customers/{customer_id}/budget", response=BudgetConfigOut)
@role_floor(ADMIN)
@records_audit("budget.set")
def put_customer_budget(request, customer_id: UUID, payload: BudgetConfigIn):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    with transaction.atomic():
        cfg = _upsert_budget(request.auth.tenant, customer, payload)
        audit_record(
            action="budget.set", tenant_id=request.auth.tenant.id,
            resource_type="budget", resource_id=customer.id,
            metadata={"scope": "customer", "customer_id": str(customer.id),
                      "cap_micros": cfg.cap_micros,
                      "enforce_mode": cfg.enforce_mode,
                      "hard_stop_pct": cfg.hard_stop_pct})
    return _budget_out(cfg)


# ---------- Per-customer billing profile (overdraft override + grant expiry) ----------


def _billing_profile_out(profile):
    return {"min_balance_micros": profile.min_balance_micros,
            "topup_grant_expiry_days": profile.topup_grant_expiry_days,
            "soft_min_balance_micros": profile.soft_min_balance_micros}


@billing_router.get("/customers/{customer_id}/billing-profile",
                 response=CustomerBillingProfileOut)
@role_floor(READ)
def get_customer_billing_profile(request, customer_id: UUID):
    _product_check(request)
    from apps.billing.wallets.models import CustomerBillingProfile
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    profile = CustomerBillingProfile.objects.filter(customer=customer).first()
    if not profile:
        return {"min_balance_micros": None, "topup_grant_expiry_days": None,
                "soft_min_balance_micros": None}
    return _billing_profile_out(profile)


@billing_router.put("/customers/{customer_id}/billing-profile",
                 response={200: CustomerBillingProfileOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("billing_profile.set")
def put_customer_billing_profile(request, customer_id: UUID, payload: CustomerBillingProfileIn):
    _product_check(request)
    from apps.billing.wallets.models import CustomerBillingProfile
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    if payload.min_balance_micros is not None and payload.min_balance_micros < 0:
        raise Problem("invalid_config",
                      "min_balance_micros must be >= 0 (allowed overdraft "
                      "magnitude), or null to inherit the tenant default")
    if payload.topup_grant_expiry_days is not None and payload.topup_grant_expiry_days <= 0:
        raise Problem("invalid_config",
                      "topup_grant_expiry_days must be > 0, or null for no expiry")
    if payload.soft_min_balance_micros is not None:
        # Soft floor (#40): the wind-down line (-soft) must sit at or above
        # the hard floor's (-hard), i.e. soft <= hard. The hard floor this
        # PUT leaves effective is the payload's own min_balance override, or
        # the tenant default when the override is null (full replace).
        from apps.billing.queries import get_billing_config
        effective_hard = payload.min_balance_micros
        if effective_hard is None:
            effective_hard = get_billing_config(request.auth.tenant.id).min_balance_micros
        if payload.soft_min_balance_micros > effective_hard:
            raise Problem("invalid_config",
                          "soft_min_balance_micros must keep the soft line at "
                          "or above the hard floor's — the value cannot exceed "
                          f"the effective min_balance_micros ({effective_hard})")
    with transaction.atomic():
        profile, _ = CustomerBillingProfile.objects.update_or_create(
            customer=customer,
            defaults={"min_balance_micros": payload.min_balance_micros,
                      "topup_grant_expiry_days": payload.topup_grant_expiry_days,
                      "soft_min_balance_micros": payload.soft_min_balance_micros})
        audit_record(
            action="billing_profile.set", tenant_id=request.auth.tenant.id,
            resource_type="billing_profile", resource_id=customer.id,
            metadata={"customer_id": str(customer.id),
                      "min_balance_micros": profile.min_balance_micros,
                      "topup_grant_expiry_days": profile.topup_grant_expiry_days,
                      "soft_min_balance_micros": profile.soft_min_balance_micros})
    return 200, _billing_profile_out(profile)


@billing_router.get("/customers/{customer_id}/budget/status", response=BudgetStatusOut)
@role_floor(READ)
def get_customer_budget_status(request, customer_id: UUID):
    _product_check(request)
    from apps.billing.gating.services.budget_service import BudgetService, _period
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    label, _s, _e = _period()
    cfg = BudgetService.resolve_config(customer)
    cap = cfg.cap_micros if cfg else 0
    try:
        spend = BudgetService.current_spend(customer.tenant_id, customer.id)
    except Exception:
        spend = 0
    pct = round(spend / cap * 100, 2) if cap > 0 else 0.0
    return {"period": label, "spend_micros": spend, "cap_micros": cap, "pct": pct,
            "enforce_mode": cfg.enforce_mode if cfg else "advisory"}


# ---------- Postpaid usage-invoice + config ----------


@billing_router.get("/customers/{customer_id}/usage-invoices", response=UsageInvoiceListResponse)
@role_floor(READ)
def list_customer_usage_invoices(request, customer_id: UUID,
                                 cursor: str = None, limit: int = 50):
    _product_check(request)
    from apps.billing.invoicing.models import CustomerUsageInvoice
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    return page(CustomerUsageInvoice.objects.filter(
                    tenant=request.auth.tenant, customer=customer),
                cursor, limit, serialize=usage_invoice_out)


@billing_router.get("/tenant/usage-invoices", response=TenantUsageInvoiceListResponse)
@role_floor(READ)
def list_tenant_usage_invoices(request, period: str = None,
                               cursor: str = None, limit: int = 50):
    _product_check(request)
    from apps.billing.invoicing.models import CustomerUsageInvoice
    qs = CustomerUsageInvoice.objects.filter(tenant=request.auth.tenant).select_related("customer")
    if period:
        import re
        from datetime import date
        if not re.fullmatch(r"\d{4}-\d{2}", period):
            raise Problem("bad_request", "period must be YYYY-MM")
        y_str, m_str = period.split("-")
        m_int = int(m_str)
        if not (1 <= m_int <= 12):
            raise Problem("bad_request", "period month must be between 01 and 12")
        qs = qs.filter(period_start=date(int(y_str), m_int, 1))
    return page(qs, cursor, limit, serialize=tenant_usage_invoice_out)


@billing_router.get("/postpaid-config", response=PostpaidConfigOut)
@role_floor(READ)
def get_postpaid_config(request):
    _product_check(request)
    from apps.billing.invoicing.models import PostpaidUsageConfig
    cfg = PostpaidUsageConfig.objects.filter(tenant=request.auth.tenant).first()
    return {"usage_line_item_group_by": cfg.usage_line_item_group_by if cfg else "",
            "consolidate_with_subscription": cfg.consolidate_with_subscription if cfg else False}


@billing_router.put("/postpaid-config", response=PostpaidConfigOut)
@role_floor(ADMIN)
@records_audit("postpaid_config.set")
def put_postpaid_config(request, payload: PostpaidConfigIn):
    _product_check(request)
    from apps.billing.invoicing.models import PostpaidUsageConfig
    # F5.5 Fix 2: both fields use None sentinel — only write the fields that
    # were explicitly provided in the PUT body.
    defaults = {}
    if payload.usage_line_item_group_by is not None:
        defaults["usage_line_item_group_by"] = payload.usage_line_item_group_by
    if payload.consolidate_with_subscription is not None:
        defaults["consolidate_with_subscription"] = payload.consolidate_with_subscription
    with transaction.atomic():
        cfg, _ = PostpaidUsageConfig.objects.update_or_create(
            tenant=request.auth.tenant, defaults=defaults)
        audit_record(
            action="postpaid_config.set", tenant_id=request.auth.tenant.id,
            resource_type="postpaid_config", resource_id=request.auth.tenant.id,
            metadata={"usage_line_item_group_by": cfg.usage_line_item_group_by,
                      "consolidate_with_subscription": cfg.consolidate_with_subscription})
    return {"usage_line_item_group_by": cfg.usage_line_item_group_by,
            "consolidate_with_subscription": cfg.consolidate_with_subscription}
