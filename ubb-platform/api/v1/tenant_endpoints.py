from typing import Optional

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
    }


@tenant_api.get("/config", response=TenantConfigOut)
def get_tenant_config(request):
    return _config_out(request.auth.tenant)


@tenant_api.patch("/config", response={200: TenantConfigOut, 422: dict})
def update_tenant_config(request, payload: TenantConfigIn):
    from django.core.exceptions import ValidationError
    from apps.metering.pricing.models import RateCard
    t = request.auth.tenant
    if payload.require_cost_card_coverage is True and not t.require_cost_card_coverage:
        if not RateCard.objects.filter(tenant=t, card_type="cost", valid_to__isnull=True).exists():
            return 422, {
                "error": "require_cost_card_coverage cannot be enabled with zero active cost rate cards",
                "code": "no_cost_cards",
            }
    if payload.billing_mode is not None:
        t.billing_mode = payload.billing_mode
    if payload.products is not None:
        t.products = payload.products
    if payload.require_cost_card_coverage is not None:
        t.require_cost_card_coverage = payload.require_cost_card_coverage
    try:
        t.save()
    except ValidationError as e:
        msg = "; ".join(
            f"{k}: {' '.join(str(x) for x in v)}" for k, v in e.message_dict.items()
        )
        return 422, {"error": msg, "code": "invalid_config"}
    return 200, _config_out(t)
