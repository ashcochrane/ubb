from typing import Optional
from uuid import UUID

from django.db import transaction
from ninja import NinjaAPI, Schema

from api.v1.pagination import apply_cursor_filter, encode_cursor
from api.v1.schemas import TenantConfigOut, TenantConfigIn
from core.auth import ApiKeyAuth
from apps.billing.tenant_billing.models import TenantBillingPeriod, TenantInvoice
from apps.platform.tenants.models import Tenant, TenantApiKey

tenant_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_tenant_v1")


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


@tenant_api.get("/billing-periods", response=TenantBillingPeriodListResponse)
def list_billing_periods(request, cursor: str = None, limit: int = 50):
    tenant = request.auth.tenant
    limit = min(max(limit, 1), 100)

    qs = TenantBillingPeriod.objects.filter(tenant=tenant).order_by("-created_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return tenant_api.create_response(request, {"error": "Invalid cursor"}, status=400)

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


@tenant_api.get("/invoices", response=TenantInvoiceListResponse)
def list_invoices(request, cursor: str = None, limit: int = 50):
    tenant = request.auth.tenant
    limit = min(max(limit, 1), 100)

    qs = TenantInvoice.objects.filter(tenant=tenant).order_by("-created_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return tenant_api.create_response(request, {"error": "Invalid cursor"}, status=400)

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


# ---- Self-serve API key lifecycle (F5.2) ----
#
# Scoping decision: every operation here is STRICTLY scoped to
# request.auth.tenant — never its sandbox sibling. A sandbox key is managed
# with a sandbox key (the sandbox IS a tenant; everything tenant-scoped
# applies to it for free). The one crossing point is mint-time routing:
# POST with is_test=True on a live key mints the key ON the sandbox sibling
# (TenantApiKey.create_key, F4.4) — that key then shows up in the SANDBOX
# tenant's list, not this one's.
#
# Revocation/rotation is instant: ApiKeyAuth resolves every request with a
# per-request DB lookup on is_active=True (no caching — do NOT add any), so
# a deactivated key 401s on its very next request.


class ApiKeyOut(Schema):
    id: str
    key_prefix: str
    label: str
    is_active: bool
    last_used_at: Optional[str] = None
    created_at: str


class ApiKeyListResponse(Schema):
    data: list[ApiKeyOut]


class ApiKeyCreateIn(Schema):
    label: str = ""
    is_test: bool = False


def _api_key_out(k):
    # NEVER the hash, NEVER the raw key — prefix + metadata only.
    return {
        "id": str(k.id),
        "key_prefix": k.key_prefix,
        "label": k.label,
        "is_active": k.is_active,
        "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        "created_at": k.created_at.isoformat(),
    }


@tenant_api.get("/api-keys", response=ApiKeyListResponse)
def list_api_keys(request):
    """All of THIS tenant's API keys (active and revoked), newest first.

    last_used_at is buffered in Redis and flushed to the DB periodically, so
    it may lag a recently-used key by up to the flush interval.
    """
    keys = TenantApiKey.objects.filter(
        tenant=request.auth.tenant).order_by("-created_at")
    return {"data": [_api_key_out(k) for k in keys]}


@tenant_api.post("/api-keys", response={201: dict, 422: dict})
def create_api_key(request, payload: ApiKeyCreateIn):
    """Mint a new API key. The RAW key is returned exactly once, here.

    is_test=True on a live key routes the mint to the tenant's sandbox
    sibling (TenantApiKey.create_key lazily provisions it, F4.4) — the new
    ubb_test_ key lives ON the sandbox tenant, so it appears in the sandbox's
    key list and is managed with a sandbox key; response tenant_id tells you
    where it landed. is_test=False on a sandbox key is a mode mismatch (422).
    """
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import TenantApiKeyCreated

    try:
        with transaction.atomic():
            key_obj, raw_key = TenantApiKey.create_key(
                request.auth.tenant, label=payload.label, is_test=payload.is_test)
            write_event(TenantApiKeyCreated(
                tenant_id=str(key_obj.tenant_id), api_key_id=str(key_obj.id),
                key_prefix=key_obj.key_prefix, label=key_obj.label))
    except ValueError as e:
        return 422, {"error": str(e)}
    return 201, {
        "id": str(key_obj.id),
        "key_prefix": key_obj.key_prefix,
        "label": key_obj.label,
        "tenant_id": str(key_obj.tenant_id),
        "api_key": raw_key,  # shown ONCE — never retrievable again
    }


@tenant_api.post("/api-keys/{key_id}/rotate", response={200: dict, 404: dict})
def rotate_api_key(request, key_id: UUID):
    """Replace a key in one transaction: mint successor, deactivate old.

    The successor keeps the old label (+ " (rotated)") and the tenant's own
    mode (a sandbox tenant rotates to a ubb_test_ key, a live tenant to a
    ubb_live_ key — never re-routed). The old key 401s on its next request;
    the new RAW key is returned exactly once.
    """
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import TenantApiKeyRotated

    tenant = request.auth.tenant
    with transaction.atomic():
        old = TenantApiKey.objects.select_for_update().filter(
            tenant=tenant, id=key_id).first()
        if old is None:
            return 404, {"error": "API key not found"}
        new_obj, raw_key = TenantApiKey.create_key(
            tenant, label=(old.label + " (rotated)").strip(),
            is_test=tenant.is_sandbox)
        old.is_active = False
        old.save(update_fields=["is_active", "updated_at"])
        write_event(TenantApiKeyRotated(
            tenant_id=str(tenant.id), old_api_key_id=str(old.id),
            new_api_key_id=str(new_obj.id), key_prefix=new_obj.key_prefix,
            label=new_obj.label))
    return 200, {
        "id": str(new_obj.id),
        "key_prefix": new_obj.key_prefix,
        "label": new_obj.label,
        "revoked_key_id": str(old.id),
        "api_key": raw_key,  # shown ONCE
    }


@tenant_api.delete("/api-keys/{key_id}", response={200: dict, 404: dict, 409: dict})
def revoke_api_key(request, key_id: UUID):
    """Soft-revoke a key (is_active=False). Idempotent on an inactive key.

    Lockout guard: revoking THIS tenant's last active key is refused with 409
    — with zero active keys the tenant could never call this API again to
    mint a replacement (rotate instead). All the tenant's key rows are locked
    in one deterministic-order query so two concurrent revokes cannot race
    past the guard together.
    """
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import TenantApiKeyRevoked

    tenant = request.auth.tenant
    with transaction.atomic():
        keys = list(TenantApiKey.objects.select_for_update().filter(
            tenant=tenant).order_by("created_at", "id"))
        key = next((k for k in keys if k.id == key_id), None)
        if key is None:
            return 404, {"error": "API key not found"}
        if key.is_active:
            if sum(1 for k in keys if k.is_active) <= 1:
                return 409, {
                    "error": "cannot revoke the tenant's last active API key "
                             "(mint or rotate a replacement first)",
                    "code": "last_active_key",
                }
            key.is_active = False
            key.save(update_fields=["is_active", "updated_at"])
            write_event(TenantApiKeyRevoked(
                tenant_id=str(tenant.id), api_key_id=str(key.id),
                key_prefix=key.key_prefix, label=key.label))
    return 200, {"id": str(key.id), "is_active": False}


# ---- Sandbox self-serve (F4.4) ----


@tenant_api.post("/sandbox", response={200: dict, 403: dict})
def create_sandbox(request):
    """Provision (or fetch) the sandbox sibling and mint a ubb_test_ API key.

    The RAW key is returned exactly once per call (each POST mints a fresh
    key — that is also the rotation path). 403 from a sandbox key: sandboxes
    cannot nest.
    """
    tenant = request.auth.tenant
    if tenant.is_sandbox:
        return 403, {"error": "sandbox tenants cannot create sandboxes (use the live key)"}
    from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox
    sandbox = get_or_create_sandbox(tenant)
    _key_obj, raw_key = TenantApiKey.create_key(sandbox, label="sandbox", is_test=True)
    return 200, {
        "sandbox_tenant_id": str(sandbox.id),
        "api_key": raw_key,
    }


@tenant_api.get("/sandbox", response={200: dict, 403: dict})
def get_sandbox(request):
    """Sandbox status for the calling live tenant (exists, id, key prefixes)."""
    tenant = request.auth.tenant
    if tenant.is_sandbox:
        return 403, {"error": "sandbox status is read with the live key"}
    sandbox = Tenant.objects.filter(parent_tenant=tenant, is_sandbox=True).first()
    if sandbox is None:
        return 200, {"exists": False, "sandbox_tenant_id": None, "key_prefixes": []}
    return 200, {
        "exists": True,
        "sandbox_tenant_id": str(sandbox.id),
        "key_prefixes": list(
            sandbox.api_keys.filter(is_active=True).values_list("key_prefix", flat=True)
        ),
    }


def _config_out(t):
    return {
        "name": t.name,
        "billing_mode": t.billing_mode,
        "products": t.products,
        "require_cost_card_coverage": t.require_cost_card_coverage,
        "default_currency": t.default_currency,
        "stripe_connected_account_id": t.stripe_connected_account_id,
        "is_active": t.is_active,
        "automatic_tax_enabled": t.automatic_tax_enabled,
        "enforcement_mode": t.enforcement_mode,
        "min_balance_micros": t.min_balance_micros,
        "run_cost_limit_micros": t.run_cost_limit_micros,
        "hard_stop_balance_micros": t.hard_stop_balance_micros,
    }


def _currency_locked_reason(t):
    """Why default_currency may no longer change, or None if it still may.

    CUR-1: once ANY money object exists for the tenant the currency is pinned
    forever. The currency of a provisioned Stripe Price is NOT stored locally
    (only the price id is), so a later cross-check against a changed tenant
    currency is impossible — the only safe rule is "no change once money
    exists". The five conditions cover every way money enters the system:
    wallet ledger rows, provisioned subscription-plan Prices, usage invoices
    pushed to Stripe, mirrored Stripe subscriptions, and ACTIVE rate cards —
    cards are currency-pinned, so a currency change would silently stop every
    card from matching and collapse COGS to the markup fallback (the exact
    meter-only failure rate cards exist to prevent).
    """
    from django.db.models import Q
    from apps.billing.invoicing.models import CustomerUsageInvoice
    from apps.billing.wallets.models import WalletTransaction
    from apps.metering.pricing.models import RateCard
    from apps.subscriptions.models import StripeSubscription, TenantBillingPlan

    if WalletTransaction.objects.filter(wallet__customer__tenant=t).exists():
        return "wallet transactions exist"
    if TenantBillingPlan.objects.filter(tenant=t).exclude(
            stripe_access_price_id="", stripe_seat_price_id="").exists():
        return "a billing plan has provisioned Stripe Prices"
    if CustomerUsageInvoice.objects.filter(tenant=t).filter(
            Q(status__in=["pushing", "pushed"]) | ~Q(stripe_invoice_id="")).exists():
        return "a usage invoice has been pushed to Stripe"
    if StripeSubscription.objects.filter(tenant=t).exists():
        return "Stripe subscriptions exist"
    if RateCard.objects.filter(tenant=t, valid_to__isnull=True).exists():
        return "active rate cards exist (cards are currency-pinned)"
    return None


@tenant_api.get("/config", response=TenantConfigOut)
def get_tenant_config(request):
    return _config_out(request.auth.tenant)


@tenant_api.patch("/config", response={200: TenantConfigOut, 409: dict, 422: dict})
def update_tenant_config(request, payload: TenantConfigIn):
    from django.core.exceptions import ValidationError
    from apps.metering.pricing.models import RateCard
    from apps.platform.tenants.models import SUPPORTED_CURRENCIES
    t = request.auth.tenant
    new_currency = None
    if payload.default_currency is not None:
        new_currency = payload.default_currency.strip().lower()
        if new_currency not in SUPPORTED_CURRENCIES:
            return 422, {
                "error": f"unsupported currency {new_currency!r}: only "
                         "2-decimal currencies are supported (zero-decimal "
                         "currencies like jpy/krw are rejected until the "
                         "minor-unit helper lands); allowed: "
                         f"{', '.join(sorted(SUPPORTED_CURRENCIES))}",
                "code": "unsupported_currency",
            }
        if new_currency != (t.default_currency or "usd").lower():
            reason = _currency_locked_reason(t)
            if reason is not None:
                return 409, {
                    "error": "default_currency cannot change once money "
                             f"exists for this tenant ({reason}); existing "
                             "wallets, Stripe Prices and invoices are "
                             "denominated in the current currency and there "
                             "is no FX/multi-currency support",
                    "code": "currency_locked",
                }
    if payload.require_cost_card_coverage is True and not t.require_cost_card_coverage:
        if not RateCard.objects.filter(tenant=t, card_type="cost", valid_to__isnull=True).exists():
            return 422, {
                "error": "require_cost_card_coverage cannot be enabled with zero active cost rate cards",
                "code": "no_cost_cards",
            }
    if payload.automatic_tax_enabled is True and not t.automatic_tax_enabled:
        # F5.3 preflight: only when the tenant is charge-ready can we ask
        # Stripe whether Tax is actually configured on the connected account.
        # Not charge-ready -> allow the flag without preflight (it only takes
        # effect at charge time, and every charge site is itself gated on
        # charge-ready — by the time a charge can happen, Stripe rejects a
        # tax-less invoice loudly and the F0.1 machinery surfaces it).
        if t.stripe_connected_account_id and t.charges_enabled:
            import stripe
            from apps.billing.stripe.services.stripe_service import (
                api_key_for_tenant, stripe_call)
            from core.exceptions import StripeFatalError
            try:
                tax_settings = stripe_call(
                    stripe.tax.Settings.retrieve,
                    api_key=api_key_for_tenant(t),
                    stripe_account=t.stripe_connected_account_id,
                )
            except StripeFatalError as e:
                return 422, {"error": f"Stripe Tax is not available on the "
                                      f"connected account: {e}",
                             "code": "stripe_tax_not_active"}
            status = getattr(tax_settings, "status", "")
            if status != "active":
                return 422, {
                    "error": "Stripe Tax is not active on the connected "
                             f"account (status={status!r}); finish Stripe Tax "
                             "setup in the Stripe dashboard first",
                    "code": "stripe_tax_not_active",
                }
    if new_currency is not None:
        t.default_currency = new_currency
    if payload.automatic_tax_enabled is not None:
        t.automatic_tax_enabled = payload.automatic_tax_enabled
    if payload.billing_mode is not None:
        t.billing_mode = payload.billing_mode
    if payload.products is not None:
        t.products = payload.products
    if payload.require_cost_card_coverage is not None:
        t.require_cost_card_coverage = payload.require_cost_card_coverage
    # Spend-safety caps. model_fields_set distinguishes an omitted key (leave
    # alone) from an explicit null (clear the cap) for the two nullable fields.
    fields_set = payload.model_fields_set
    if payload.min_balance_micros is not None:
        if payload.min_balance_micros < 0:
            return 422, {"error": "min_balance_micros must be >= 0 (it is the "
                                  "allowed overdraft magnitude, not a floor)",
                         "code": "invalid_config"}
        t.min_balance_micros = payload.min_balance_micros
    if "run_cost_limit_micros" in fields_set:
        if payload.run_cost_limit_micros is not None and payload.run_cost_limit_micros <= 0:
            return 422, {"error": "run_cost_limit_micros must be > 0, or null for no cap",
                         "code": "invalid_config"}
        t.run_cost_limit_micros = payload.run_cost_limit_micros
    if "hard_stop_balance_micros" in fields_set:
        t.hard_stop_balance_micros = payload.hard_stop_balance_micros
    enforcement_changed = False
    if payload.enforcement_mode is not None:
        from apps.platform.tenants.models import ENFORCEMENT_MODE_CHOICES
        valid_modes = {c[0] for c in ENFORCEMENT_MODE_CHOICES}
        if payload.enforcement_mode not in valid_modes:
            return 422, {"error": f"enforcement_mode must be one of {sorted(valid_modes)}",
                         "code": "invalid_config"}
        enforcement_changed = payload.enforcement_mode != t.enforcement_mode
        t.enforcement_mode = payload.enforcement_mode
    try:
        t.save()
    except ValidationError as e:
        msg = "; ".join(
            f"{k}: {' '.join(str(x) for x in v)}" for k, v in e.message_dict.items()
        )
        return 422, {"error": msg, "code": "invalid_config"}
    if enforcement_changed:
        # D17: clear stale Tier-2 keys so the new mode starts clean (esp. a
        # leftover stop flag that could wrongly suspend after a re-enable).
        from django.db import transaction
        from apps.billing.gating.services.live_ledger_service import LiveLedgerService
        transaction.on_commit(lambda: LiveLedgerService.cleanup_keys(t))
    return 200, _config_out(t)
