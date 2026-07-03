from datetime import date
from typing import Optional
from uuid import UUID

from ninja import NinjaAPI, Schema

from api.v1.pagination import apply_cursor_filter, encode_cursor
from api.v1.schemas import (
    PreCheckRequest, PreCheckResponse,
    BalanceResponse,
    ConfigureAutoTopUpRequest,
    CreateTopUpRequest,
    WithdrawRequest,
    RefundRequest,
    DebitRequest, CreditRequest, DebitCreditResponse,
    CreateGrantRequest, GrantOut, PaginatedGrants,
    RevenueAnalyticsResponse,
    BudgetConfigIn, BudgetConfigOut, BudgetStatusOut,
    CustomerBillingProfileIn, CustomerBillingProfileOut,
    UsageInvoiceOut, PostpaidConfigIn, PostpaidConfigOut,
)
from core.auth import ApiKeyAuth, ProductAccess
from apps.platform.customers.models import Customer
from apps.billing.topups.models import AutoTopUpConfig
from apps.billing.gating.services.risk_service import RiskService
from apps.billing.connectors.stripe.stripe_api import create_checkout_session
from apps.billing.tenant_billing.models import TenantBillingPeriod, TenantInvoice
from django.shortcuts import get_object_or_404

billing_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_billing_v1")

_product_check = ProductAccess("billing")


# ---------- Customer billing endpoints ----------


@billing_api.get("/customers/{customer_id}/balance", response=BalanceResponse)
def get_balance(request, customer_id: str):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    from apps.billing.wallets.models import Wallet
    from apps.billing.wallets.grants import GrantLedger
    try:
        wallet = Wallet.objects.get(customer=customer)
        return {"balance_micros": wallet.balance_micros, "currency": wallet.currency,
                **GrantLedger.balance_summary(wallet)}
    except Wallet.DoesNotExist:
        # CUR-1: no-wallet fallback reports the tenant currency, not a literal USD.
        return {"balance_micros": 0,
                "currency": (request.auth.tenant.default_currency or "usd").lower(),
                "promo_micros": 0, "expiring_micros": 0, "next_expiry_at": None}


@billing_api.post("/debit", response=DebitCreditResponse)
def debit(request, payload: DebitRequest):
    _product_check(request)
    from django.db import transaction
    from apps.billing.locking import lock_for_billing
    from apps.billing.wallets.grants import GrantLedger
    from apps.billing.wallets.models import WalletTransaction

    customer = get_object_or_404(
        Customer, external_id=payload.customer_id, tenant=request.auth.tenant
    )

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer.id)
        GrantLedger.expire_due(wallet)  # F4.3 lazy expiry: never consume a due lot

        if payload.idempotency_key:
            existing = WalletTransaction.objects.filter(
                wallet=wallet, idempotency_key=payload.idempotency_key,
            ).first()
            if existing:
                return {"new_balance_micros": wallet.balance_micros, "transaction_id": str(existing.id)}

        wallet.balance_micros -= payload.amount_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])

        txn = WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="DEBIT",
            amount_micros=-payload.amount_micros,
            balance_after_micros=wallet.balance_micros,
            description="External debit",
            reference_id=payload.reference,
            idempotency_key=payload.idempotency_key or None,
        )
        GrantLedger.allocate(wallet, txn, payload.amount_micros)  # F4.3: usage order

    return {"new_balance_micros": wallet.balance_micros, "transaction_id": str(txn.id)}


@billing_api.post("/credit", response=DebitCreditResponse)
def credit(request, payload: CreditRequest):
    """Credit the wallet with LEGACY BASE money (non-expiring, no grant lot).

    Deliberately untouched by F4.3: base is derived (balance minus active
    grant remainders), so an ADJUSTMENT credit simply grows base. Tenants who
    want expiring or promo credit use POST /customers/{id}/grants instead.
    """
    _product_check(request)
    from django.db import transaction
    from apps.billing.locking import lock_for_billing
    from apps.billing.wallets.models import WalletTransaction

    customer = get_object_or_404(
        Customer, external_id=payload.customer_id, tenant=request.auth.tenant
    )

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer.id)

        if payload.idempotency_key:
            existing = WalletTransaction.objects.filter(
                wallet=wallet, idempotency_key=payload.idempotency_key,
            ).first()
            if existing:
                return {"new_balance_micros": wallet.balance_micros, "transaction_id": str(existing.id)}

        wallet.balance_micros += payload.amount_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])

        txn = WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="ADJUSTMENT",
            amount_micros=payload.amount_micros,
            balance_after_micros=wallet.balance_micros,
            description=f"Credit: {payload.source}",
            reference_id=payload.reference,
            idempotency_key=payload.idempotency_key or None,
        )
        # Tier-2 (P2/D20): mirror the manual credit onto the live balance after
        # commit (mandatory — MIN-merge cannot re-raise a missed credit). No-op
        # when enforcement is off / postpaid.
        from apps.billing.gating.services.live_ledger_service import LiveLedgerService
        transaction.on_commit(
            lambda oid=wallet.customer_id, t=request.auth.tenant, amt=payload.amount_micros:
            LiveLedgerService.credit(oid, t, amt))

    return {"new_balance_micros": wallet.balance_micros, "transaction_id": str(txn.id)}


@billing_api.put("/customers/{customer_id}/auto-top-up")
def configure_auto_top_up(request, customer_id: str, payload: ConfigureAutoTopUpRequest):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    AutoTopUpConfig.objects.update_or_create(
        customer=customer,
        defaults={
            "is_enabled": payload.is_enabled,
            "trigger_threshold_micros": payload.trigger_threshold_micros,
            "top_up_amount_micros": payload.top_up_amount_micros,
        },
    )
    return {"status": "ok"}


@billing_api.post("/customers/{customer_id}/top-up")
def create_top_up(request, customer_id: str, payload: CreateTopUpRequest):
    _product_check(request)
    from apps.billing.topups.models import TopUpAttempt

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    tenant = request.auth.tenant

    from apps.platform.queries import get_tenant_stripe_account, get_customer_stripe_id
    if get_tenant_stripe_account(tenant.id):
        # Stripe connector is active — create checkout session
        if not get_customer_stripe_id(customer.id):
            return billing_api.create_response(
                request, {"error": "Customer has no stripe_customer_id"}, status=400
            )

        attempt = TopUpAttempt.objects.create(
            customer=customer,
            amount_micros=payload.amount_micros,
            trigger="manual",
            status="pending",
        )

        checkout_url = create_checkout_session(
            customer, payload.amount_micros, attempt,
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
        )
        return {"checkout_url": checkout_url}
    else:
        # No connector — emit event for tenant to handle
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import TopUpRequested

        write_event(TopUpRequested(
            tenant_id=str(tenant.id),
            customer_id=str(customer.id),
            amount_micros=payload.amount_micros,
            trigger="manual",
            success_url=getattr(payload, "success_url", "") or "",
            cancel_url=getattr(payload, "cancel_url", "") or "",
        ))
        return billing_api.create_response(
            request,
            {"status": "topup_requested", "message": "Top-up request sent to tenant"},
            status=202,
        )


@billing_api.post("/customers/{customer_id}/withdraw")
def withdraw(request, customer_id: str, payload: WithdrawRequest):
    """Withdraw base + paid money. Promo credit is NOT withdrawable (F4.3):
    availability is balance minus active promo remainders."""
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    from django.db import IntegrityError, transaction
    from apps.billing.locking import lock_for_billing
    from apps.billing.wallets.grants import GrantLedger
    from apps.billing.wallets.models import WalletTransaction
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import WithdrawalRequested

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer.id)
        GrantLedger.expire_due(wallet)  # F4.3 lazy expiry

        # Check idempotency
        existing = WalletTransaction.objects.filter(
            wallet=wallet, idempotency_key=payload.idempotency_key
        ).first()
        if existing:
            return {"transaction_id": str(existing.id), "balance_micros": wallet.balance_micros}

        if wallet.balance_micros - GrantLedger.promo_remaining(wallet) < payload.amount_micros:
            return billing_api.create_response(
                request, {"error": "Insufficient balance"}, status=400
            )

        wallet.balance_micros -= payload.amount_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])

        txn = WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="WITHDRAWAL",
            amount_micros=-payload.amount_micros,
            balance_after_micros=wallet.balance_micros,
            description=payload.description or "Withdrawal",
            idempotency_key=payload.idempotency_key,
        )
        GrantLedger.allocate(wallet, txn, payload.amount_micros,
                             exclude_promo=True, allocation_type="withdrawal")

        write_event(WithdrawalRequested(
            tenant_id=str(request.auth.tenant.id),
            customer_id=str(customer.id),
            amount_micros=payload.amount_micros,
            transaction_id=str(txn.id),
            idempotency_key=payload.idempotency_key,
        ))

    return {"transaction_id": str(txn.id), "balance_micros": wallet.balance_micros}


@billing_api.post("/pre-check", response=PreCheckResponse)
def pre_check(request, payload: PreCheckRequest):
    _product_check(request)
    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)
    result = RiskService.check(
        customer,
        create_run=payload.start_run,
        run_metadata=payload.run_metadata,
        external_run_id=payload.external_run_id,
    )
    return result


@billing_api.post("/customers/{customer_id}/refund")
def refund_usage(request, customer_id: str, payload: RefundRequest):
    """Refund a usage charge. LOT-AWARE (F4.3): the slices of the original
    USAGE_DEDUCTION that were funded by still-live grant lots are re-funded
    back into those lots (promo refunds restore the promo lot — they never
    become withdrawable cash); only the base-funded remainder, plus shares
    from since-expired/voided lots, lands as base credit."""
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    from django.db import transaction
    from apps.billing.locking import lock_for_billing
    from apps.billing.wallets.grants import GrantLedger
    from apps.billing.wallets.models import WalletTransaction
    from apps.metering.queries import get_usage_event_cost
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import RefundRequested

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer.id)
        GrantLedger.expire_due(wallet)  # F4.3 lazy expiry: a due lot expires
        # first, so its share of the refund correctly lands as base below.

        # Idempotency on WalletTransaction
        existing_txn = WalletTransaction.objects.filter(
            wallet=wallet, idempotency_key=payload.idempotency_key
        ).first()
        if existing_txn:
            return {"refund_id": existing_txn.reference_id, "balance_micros": wallet.balance_micros}

        # Look up cost via metering query interface (tenant-scoped)
        cost = get_usage_event_cost(payload.usage_event_id, tenant_id=request.auth.tenant.id)
        if cost is None:
            return billing_api.create_response(request, {"error": "Usage event not found"}, status=404)

        wallet.balance_micros += cost
        wallet.save(update_fields=["balance_micros", "updated_at"])
        # Tier-2 (P2/D20): mirror the usage-refund credit onto the live balance
        # (mandatory — MIN-merge cannot re-raise a missed credit).
        from apps.billing.gating.services.live_ledger_service import LiveLedgerService
        transaction.on_commit(
            lambda oid=wallet.customer_id, t=request.auth.tenant, amt=cost:
            LiveLedgerService.credit(oid, t, amt))

        txn = WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="REFUND",
            amount_micros=cost,
            balance_after_micros=wallet.balance_micros,
            description=f"Refund: {payload.usage_event_id}",
            reference_id=str(payload.usage_event_id),
            idempotency_key=payload.idempotency_key,
        )

        # F4.3 lot-aware re-fund: find the original deduction via its pinned
        # usage_event_id column and restore its GrantAllocation slices into
        # the still-live lots (refunded_micros caps make a second refund of
        # the same event — under a different idempotency key — land as base).
        original = WalletTransaction.objects.filter(
            wallet=wallet, transaction_type="USAGE_DEDUCTION",
            usage_event_id=payload.usage_event_id,
        ).first()
        GrantLedger.refund(wallet, original)

        # Emit outbox event for metering to create Refund record
        write_event(RefundRequested(
            tenant_id=str(request.auth.tenant.id),
            customer_id=str(customer.id),
            usage_event_id=str(payload.usage_event_id),
            refund_amount_micros=cost,
            reason=payload.reason,
            idempotency_key=payload.idempotency_key,
        ))

    return {"refund_id": str(txn.id), "balance_micros": wallet.balance_micros}


@billing_api.get("/customers/{customer_id}/transactions")
def get_transactions(request, customer_id: str, cursor: str = None, limit: int = 50):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    limit = min(max(limit, 1), 100)

    from apps.billing.wallets.models import Wallet
    try:
        wallet = Wallet.objects.get(customer=customer)
    except Wallet.DoesNotExist:
        return {"data": [], "next_cursor": None, "has_more": False}

    qs = wallet.transactions.all().order_by("-created_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return billing_api.create_response(request, {"error": "Invalid cursor"}, status=400)

    txns = list(qs[:limit + 1])
    has_more = len(txns) > limit
    txns = txns[:limit]

    next_cursor = None
    if has_more and txns:
        last = txns[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [
            {
                "id": t.id,
                "transaction_type": t.transaction_type,
                "amount_micros": t.amount_micros,
                "balance_after_micros": t.balance_after_micros,
                "description": t.description,
                "reference_id": t.reference_id,
                "created_at": t.created_at.isoformat(),
            }
            for t in txns
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


# ---------- Credit grants (F4.3) ----------


def _grant_out(grant, *, balance_micros=None, transaction_id=None):
    return {
        "id": str(grant.id),
        "kind": grant.kind,
        "granted_micros": grant.granted_micros,
        "remaining_micros": grant.remaining_micros,
        "expired_micros": grant.expired_micros,
        "voided_micros": grant.voided_micros,
        "currency": grant.currency,
        "status": grant.status,
        "source": grant.source,
        "expires_at": grant.expires_at.isoformat() if grant.expires_at else None,
        "warning_sent_at": grant.warning_sent_at.isoformat() if grant.warning_sent_at else None,
        "created_at": grant.created_at.isoformat(),
        "balance_micros": balance_micros,
        "transaction_id": transaction_id,
    }


@billing_api.post("/customers/{customer_id}/grants", response=GrantOut)
def create_grant(request, customer_id: UUID, payload: CreateGrantRequest):
    """Create an expiring (or non-expiring) credit grant lot on the billing
    owner's wallet. Exactly-once via grant:{idempotency_key} — the GRANT
    WalletTransaction and the CreditGrant share one savepoint."""
    _product_check(request)
    from datetime import timedelta
    from django.db import IntegrityError, transaction
    from django.utils import timezone
    from apps.billing.locking import lock_for_billing
    from apps.billing.wallets.grants import GrantLedger
    from apps.billing.wallets.models import CreditGrant, WalletTransaction

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    if payload.expires_at is not None and payload.expires_in_days is not None:
        return billing_api.create_response(
            request, {"error": "Pass expires_at OR expires_in_days, not both"}, status=400)
    if payload.expires_at is not None:
        if payload.expires_at.tzinfo is None:
            return billing_api.create_response(
                request, {"error": "expires_at must be timezone-aware"}, status=400)
        if payload.expires_at <= timezone.now():
            return billing_api.create_response(
                request, {"error": "expires_at must be in the future"}, status=400)
        expires_at = payload.expires_at
    elif payload.expires_in_days is not None:
        expires_at = timezone.now() + timedelta(days=payload.expires_in_days)
    else:
        expires_at = None  # non-expiring lot

    owner = customer.resolve_billing_owner()
    key = f"grant:{payload.idempotency_key}"
    with transaction.atomic():
        wallet, owner = lock_for_billing(owner.id)
        existing = WalletTransaction.objects.filter(wallet=wallet, idempotency_key=key).first()
        if existing is None:
            new_balance = wallet.balance_micros + payload.amount_micros
            try:
                with transaction.atomic():  # savepoint: txn + grant land together
                    txn = WalletTransaction.objects.create(
                        wallet=wallet,
                        transaction_type="GRANT",
                        amount_micros=payload.amount_micros,
                        balance_after_micros=new_balance,
                        description=payload.description or f"Credit grant ({payload.kind})",
                        reference_id=payload.idempotency_key,
                        idempotency_key=key,
                    )
                    grant = GrantLedger.create_grant(
                        wallet, request.auth.tenant.id, kind=payload.kind,
                        amount_micros=payload.amount_micros, expires_at=expires_at,
                        source="api", source_reference=payload.idempotency_key, txn=txn)
            except IntegrityError:
                existing = WalletTransaction.objects.get(wallet=wallet, idempotency_key=key)
            else:
                wallet.balance_micros = new_balance
                wallet.save(update_fields=["balance_micros", "updated_at"])
                # Tier-2 (P2/D20): mirror the grant credit onto the live balance
                # (grants raise spendable prepaid balance; MIN-merge cannot
                # re-raise a missed credit).
                from apps.billing.gating.services.live_ledger_service import LiveLedgerService
                transaction.on_commit(
                    lambda oid=wallet.customer_id, t=request.auth.tenant, amt=payload.amount_micros:
                    LiveLedgerService.credit(oid, t, amt))
                return _grant_out(grant, balance_micros=wallet.balance_micros,
                                  transaction_id=str(txn.id))
        # Idempotent replay: return the grant created with the original txn.
        grant = CreditGrant.objects.filter(source_transaction=existing).first()
        if grant is None:
            return billing_api.create_response(
                request, {"error": "idempotency_key already used by a non-grant transaction"},
                status=409)
        return _grant_out(grant, balance_micros=wallet.balance_micros,
                          transaction_id=str(existing.id))


@billing_api.get("/customers/{customer_id}/grants", response=PaginatedGrants)
def list_grants(request, customer_id: UUID, status: str = None,
                cursor: str = None, limit: int = 50):
    """List the billing owner's grant lots (newest first), optional status filter."""
    _product_check(request)
    from apps.billing.wallets.models import CreditGrant, Wallet

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    limit = min(max(limit, 1), 100)
    owner = customer.resolve_billing_owner()
    wallet = Wallet.objects.filter(customer=owner).first()
    if wallet is None:
        return {"data": [], "next_cursor": None, "has_more": False}

    qs = CreditGrant.objects.filter(wallet=wallet).order_by("-created_at", "-id")
    if status:
        qs = qs.filter(status=status)

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return billing_api.create_response(request, {"error": "Invalid cursor"}, status=400)

    grants = list(qs[:limit + 1])
    has_more = len(grants) > limit
    grants = grants[:limit]

    next_cursor = None
    if has_more and grants:
        last = grants[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {"data": [_grant_out(g) for g in grants],
            "next_cursor": next_cursor, "has_more": has_more}


@billing_api.post("/customers/{customer_id}/grants/{grant_id}/void", response=GrantOut)
def void_grant(request, customer_id: UUID, grant_id: UUID):
    """Void a grant: debit its remaining (clamped so the balance never goes
    negative, like expiry) and retire the lot. Exactly-once via
    grant_void:{grant_id}; replays return the voided lot unchanged."""
    _product_check(request)
    from django.db import IntegrityError, transaction
    from apps.billing.locking import lock_for_billing
    from apps.billing.wallets.grants import GrantLedger
    from apps.billing.wallets.models import CreditGrant, WalletTransaction

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    owner = customer.resolve_billing_owner()
    with transaction.atomic():
        wallet, owner = lock_for_billing(owner.id)
        grant = get_object_or_404(
            CreditGrant, id=grant_id, wallet=wallet, tenant=request.auth.tenant)
        GrantLedger.expire_due(wallet)  # a due lot expires; void then no-ops
        grant.refresh_from_db()
        if grant.status != "active":
            return _grant_out(grant, balance_micros=wallet.balance_micros)
        # Clamp like expiry (G3): voiding never drives the balance negative.
        debit = min(grant.remaining_micros, max(wallet.balance_micros, 0))
        new_balance = wallet.balance_micros - debit
        try:
            with transaction.atomic():  # savepoint
                txn = WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type="GRANT_VOID",
                    amount_micros=-debit,
                    balance_after_micros=new_balance,
                    description=f"Credit grant voided ({grant.kind})",
                    reference_id=str(grant.id),
                    idempotency_key=f"grant_void:{grant.id}",
                )
        except IntegrityError:
            grant.refresh_from_db()
            return _grant_out(grant, balance_micros=wallet.balance_micros)
        wallet.balance_micros = new_balance
        wallet.save(update_fields=["balance_micros", "updated_at"])
        # += (not =): a partial clawback may already have moved some of this
        # lot into voided_micros — voiding must accumulate, never clobber.
        grant.voided_micros += grant.remaining_micros
        grant.remaining_micros = 0
        grant.status = "voided"
        grant.save(update_fields=["voided_micros", "remaining_micros", "status", "updated_at"])
        return _grant_out(grant, balance_micros=wallet.balance_micros,
                          transaction_id=str(txn.id))


# ---------- Tenant billing endpoints ----------


class TenantBillingPeriodOut(Schema):
    id: str
    period_start: str
    period_end: str
    status: str
    total_usage_cost_micros: int
    event_count: int
    platform_fee_micros: int


class TenantBillingPeriodListResponse(Schema):
    data: list[TenantBillingPeriodOut]
    next_cursor: Optional[str] = None
    has_more: bool


class TenantInvoiceOut(Schema):
    id: str
    billing_period_id: str
    stripe_invoice_id: str
    total_amount_micros: int
    status: str
    created_at: str


class TenantInvoiceListResponse(Schema):
    data: list[TenantInvoiceOut]
    next_cursor: Optional[str] = None
    has_more: bool


@billing_api.get("/tenant/billing-periods", response=TenantBillingPeriodListResponse)
def list_billing_periods(request, cursor: str = None, limit: int = 50):
    _product_check(request)
    tenant = request.auth.tenant
    limit = min(max(limit, 1), 100)

    qs = TenantBillingPeriod.objects.filter(tenant=tenant).order_by("-created_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return billing_api.create_response(request, {"error": "Invalid cursor"}, status=400)

    periods = list(qs[:limit + 1])
    has_more = len(periods) > limit
    periods = periods[:limit]

    next_cursor = None
    if has_more and periods:
        last = periods[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [
            {
                "id": str(p.id),
                "period_start": p.period_start.isoformat(),
                "period_end": p.period_end.isoformat(),
                "status": p.status,
                "total_usage_cost_micros": p.total_usage_cost_micros,
                "event_count": p.event_count,
                "platform_fee_micros": p.platform_fee_micros,
            }
            for p in periods
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@billing_api.get("/tenant/invoices", response=TenantInvoiceListResponse)
def list_invoices(request, cursor: str = None, limit: int = 50):
    _product_check(request)
    tenant = request.auth.tenant
    limit = min(max(limit, 1), 100)

    qs = TenantInvoice.objects.filter(tenant=tenant).order_by("-created_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return billing_api.create_response(request, {"error": "Invalid cursor"}, status=400)

    invoices = list(qs[:limit + 1])
    has_more = len(invoices) > limit
    invoices = invoices[:limit]

    next_cursor = None
    if has_more and invoices:
        last = invoices[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [
            {
                "id": str(inv.id),
                "billing_period_id": str(inv.billing_period_id),
                "stripe_invoice_id": inv.stripe_invoice_id,
                "total_amount_micros": inv.total_amount_micros,
                "status": inv.status,
                "created_at": inv.created_at.isoformat(),
            }
            for inv in invoices
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


# ---------- Analytics ----------


@billing_api.get("/analytics/revenue", response=RevenueAnalyticsResponse)
def revenue_analytics(request, start_date: date = None, end_date: date = None):
    _product_check(request)
    from apps.metering.queries import get_revenue_analytics
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


@billing_api.get("/budget", response=BudgetConfigOut)
def get_tenant_budget(request):
    _product_check(request)
    from apps.billing.gating.models import BudgetConfig
    cfg = BudgetConfig.objects.filter(tenant=request.auth.tenant, customer__isnull=True).first()
    if not cfg:
        return {"cap_micros": 0, "enforce_mode": "advisory", "hard_stop_pct": 100,
                "alert_levels": [50, 80, 100, 110], "fail_closed": False}
    return _budget_out(cfg)


@billing_api.put("/budget", response=BudgetConfigOut)
def put_tenant_budget(request, payload: BudgetConfigIn):
    _product_check(request)
    return _budget_out(_upsert_budget(request.auth.tenant, None, payload))


@billing_api.get("/customers/{customer_id}/budget", response=BudgetConfigOut)
def get_customer_budget(request, customer_id: UUID):
    _product_check(request)
    from apps.billing.gating.models import BudgetConfig
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    cfg = BudgetConfig.objects.filter(tenant=request.auth.tenant, customer=customer).first()
    if not cfg:
        return {"cap_micros": 0, "enforce_mode": "advisory", "hard_stop_pct": 100,
                "alert_levels": [50, 80, 100, 110], "fail_closed": False}
    return _budget_out(cfg)


@billing_api.put("/customers/{customer_id}/budget", response=BudgetConfigOut)
def put_customer_budget(request, customer_id: UUID, payload: BudgetConfigIn):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    return _budget_out(_upsert_budget(request.auth.tenant, customer, payload))


# ---------- Per-customer billing profile (overdraft override + grant expiry) ----------


def _billing_profile_out(profile):
    return {"min_balance_micros": profile.min_balance_micros,
            "topup_grant_expiry_days": profile.topup_grant_expiry_days}


@billing_api.get("/customers/{customer_id}/billing-profile",
                 response=CustomerBillingProfileOut)
def get_customer_billing_profile(request, customer_id: UUID):
    _product_check(request)
    from apps.billing.wallets.models import CustomerBillingProfile
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    profile = CustomerBillingProfile.objects.filter(customer=customer).first()
    if not profile:
        return {"min_balance_micros": None, "topup_grant_expiry_days": None}
    return _billing_profile_out(profile)


@billing_api.put("/customers/{customer_id}/billing-profile",
                 response={200: CustomerBillingProfileOut, 422: dict})
def put_customer_billing_profile(request, customer_id: UUID, payload: CustomerBillingProfileIn):
    _product_check(request)
    from apps.billing.wallets.models import CustomerBillingProfile
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    if payload.min_balance_micros is not None and payload.min_balance_micros < 0:
        return 422, {"error": "min_balance_micros must be >= 0 (allowed overdraft "
                              "magnitude), or null to inherit the tenant default",
                     "code": "invalid_config"}
    if payload.topup_grant_expiry_days is not None and payload.topup_grant_expiry_days <= 0:
        return 422, {"error": "topup_grant_expiry_days must be > 0, or null for no expiry",
                     "code": "invalid_config"}
    profile, _ = CustomerBillingProfile.objects.update_or_create(
        customer=customer,
        defaults={"min_balance_micros": payload.min_balance_micros,
                  "topup_grant_expiry_days": payload.topup_grant_expiry_days})
    return 200, _billing_profile_out(profile)


@billing_api.get("/customers/{customer_id}/budget/status", response=BudgetStatusOut)
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


@billing_api.get("/customers/{customer_id}/usage-invoices", response=list[UsageInvoiceOut])
def list_customer_usage_invoices(request, customer_id: UUID):
    _product_check(request)
    from apps.billing.invoicing.models import CustomerUsageInvoice
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    rows = CustomerUsageInvoice.objects.filter(tenant=request.auth.tenant, customer=customer).order_by("-period_start")
    return [{"period_start": r.period_start.isoformat(), "period_end": r.period_end.isoformat(),
             "total_billed_micros": r.total_billed_micros, "currency": r.currency, "status": r.status,
             "stripe_invoice_id": r.stripe_invoice_id, "skip_reason": r.skip_reason,
             "push_attempts": r.push_attempts, "last_attempt_error": r.last_attempt_error}
            for r in rows]


@billing_api.get("/tenant/usage-invoices")
def list_tenant_usage_invoices(request, period: str = None):
    _product_check(request)
    from apps.billing.invoicing.models import CustomerUsageInvoice
    qs = CustomerUsageInvoice.objects.filter(tenant=request.auth.tenant).select_related("customer")
    if period:
        import re
        from datetime import date
        from ninja.errors import HttpError
        if not re.fullmatch(r"\d{4}-\d{2}", period):
            raise HttpError(400, "period must be YYYY-MM")
        y_str, m_str = period.split("-")
        m_int = int(m_str)
        if not (1 <= m_int <= 12):
            raise HttpError(400, "period month must be between 01 and 12")
        qs = qs.filter(period_start=date(int(y_str), m_int, 1))
    return {"invoices": [{"customer_id": str(r.customer_id), "external_id": r.customer.external_id,
             "period_start": r.period_start.isoformat(), "total_billed_micros": r.total_billed_micros,
             "status": r.status, "stripe_invoice_id": r.stripe_invoice_id, "skip_reason": r.skip_reason,
             "push_attempts": r.push_attempts, "last_attempt_error": r.last_attempt_error}
            for r in qs.order_by("-period_start")]}


@billing_api.get("/postpaid-config", response=PostpaidConfigOut)
def get_postpaid_config(request):
    _product_check(request)
    from apps.billing.invoicing.models import PostpaidUsageConfig
    cfg = PostpaidUsageConfig.objects.filter(tenant=request.auth.tenant).first()
    return {"usage_line_item_group_by": cfg.usage_line_item_group_by if cfg else "",
            "consolidate_with_subscription": cfg.consolidate_with_subscription if cfg else False}


@billing_api.put("/postpaid-config", response=PostpaidConfigOut)
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
    cfg, _ = PostpaidUsageConfig.objects.update_or_create(
        tenant=request.auth.tenant, defaults=defaults)
    return {"usage_line_item_group_by": cfg.usage_line_item_group_by,
            "consolidate_with_subscription": cfg.consolidate_with_subscription}
