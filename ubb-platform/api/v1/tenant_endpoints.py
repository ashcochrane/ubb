from typing import Optional
from uuid import UUID

from django.db import transaction
from ninja import Router, Schema

from api.v1.pagination import paginate
from api.v1.schemas import (
    TenantBillingPeriodListResponse,
    TenantBillingPeriodOut,
    TenantConfigIn,
    TenantConfigOut,
    TenantInvoiceListResponse,
    TenantInvoiceOut,
)
from core.auth import ApiKeyAuth, require_role
from core.problems import Problem, ProblemOut
from apps.billing.tenant_billing.models import TenantBillingPeriod, TenantInvoice
from apps.platform.membership import services as membership_services
from apps.platform.membership.models import Invitation, Member
from apps.platform.membership.roles import ADMIN, READ
from apps.platform.tenants.models import Tenant, TenantApiKey

tenant_router = Router(auth=ApiKeyAuth())


@tenant_router.get("/billing-periods", response=TenantBillingPeriodListResponse)
def list_billing_periods(request, cursor: str = None, limit: int = 50):
    tenant = request.auth.tenant

    periods, next_cursor, has_more = paginate(
        TenantBillingPeriod.objects.filter(tenant=tenant), cursor, limit)

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


@tenant_router.get("/invoices", response=TenantInvoiceListResponse)
def list_invoices(request, cursor: str = None, limit: int = 50):
    tenant = request.auth.tenant

    invoices, next_cursor, has_more = paginate(
        TenantInvoice.objects.filter(tenant=tenant), cursor, limit)

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
    next_cursor: Optional[str] = None
    has_more: bool


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


@tenant_router.get("/api-keys", response=ApiKeyListResponse)
def list_api_keys(request, cursor: str = None, limit: int = 50):
    """THIS tenant's API keys (active and revoked), newest first.

    last_used_at is buffered in Redis and flushed to the DB periodically, so
    it may lag a recently-used key by up to the flush interval.
    """
    keys, next_cursor, has_more = paginate(
        TenantApiKey.objects.filter(tenant=request.auth.tenant), cursor, limit)
    return {"data": [_api_key_out(k) for k in keys],
            "next_cursor": next_cursor, "has_more": has_more}


@tenant_router.post("/api-keys", response={201: dict, 422: ProblemOut})
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
        raise Problem("validation_error", str(e))
    return 201, {
        "id": str(key_obj.id),
        "key_prefix": key_obj.key_prefix,
        "label": key_obj.label,
        "tenant_id": str(key_obj.tenant_id),
        "api_key": raw_key,  # shown ONCE — never retrievable again
    }


@tenant_router.post("/api-keys/{key_id}/rotate", response={200: dict, 404: ProblemOut})
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
            raise Problem("not_found", "API key not found")
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


@tenant_router.delete("/api-keys/{key_id}", response={200: dict, 404: ProblemOut, 409: ProblemOut})
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
            raise Problem("not_found", "API key not found")
        if key.is_active:
            if sum(1 for k in keys if k.is_active) <= 1:
                raise Problem(
                    "last_active_key",
                    "cannot revoke the tenant's last active API key "
                    "(mint or rotate a replacement first)")
            key.is_active = False
            key.save(update_fields=["is_active", "updated_at"])
            write_event(TenantApiKeyRevoked(
                tenant_id=str(tenant.id), api_key_id=str(key.id),
                key_prefix=key.key_prefix, label=key.label))
    return 200, {"id": str(key.id), "is_active": False}


# ---- Members & invitations (identity build 1, #79) ----
#
# Two tenant-principal schemes reach every route here: a tenant API key (always
# Admin today) or a Clerk member token. The role floor is bound per route — the
# only floors that bind in this build:
#   * invitations create/list/revoke — Admin (per the #74 carve),
#   * members list — Read (any tenant principal).
# Member role-change/removal is identity build 2 (it needs the last-Admin
# guard), so there is no PATCH/DELETE on a member here.


class InvitationCreateIn(Schema):
    email: str
    role: str


class InvitationOut(Schema):
    id: str
    email: str
    role: str
    status: str
    created_at: str


class InvitationListResponse(Schema):
    data: list[InvitationOut]
    next_cursor: Optional[str] = None
    has_more: bool


class MemberOut(Schema):
    id: str
    email: str
    role: str
    status: str
    # Empty until the member activates on first Clerk login.
    clerk_user_id: str = ""
    activated_at: Optional[str] = None
    created_at: str


class MemberListResponse(Schema):
    data: list[MemberOut]
    next_cursor: Optional[str] = None
    has_more: bool


def _invitation_out(inv):
    return {
        "id": str(inv.id),
        "email": inv.email,
        "role": inv.role,
        "status": inv.status,
        "created_at": inv.created_at.isoformat(),
    }


def _member_out(m):
    return {
        "id": str(m.id),
        "email": m.email,
        "role": m.role,
        "status": m.status,
        "clerk_user_id": m.clerk_user_id,
        "activated_at": m.activated_at.isoformat() if m.activated_at else None,
        "created_at": m.created_at.isoformat(),
    }


@tenant_router.post(
    "/invitations",
    response={201: InvitationOut, 403: ProblemOut, 409: ProblemOut, 422: ProblemOut},
)
def create_invitation(request, payload: InvitationCreateIn):
    """Invite a teammate by email with a role (Admin only).

    Creates a first-class Invitation and a pending Member; the invitee signs up
    through Clerk and activates on first login (matched by email). 409 if the
    email is already a member or already has a pending invite; 422 on an unknown
    role.
    """
    require_role(request, ADMIN)
    inviter = request.auth if isinstance(request.auth, Member) else None
    invitation = membership_services.invite_member(
        request.auth.tenant, payload.email, payload.role,
        invited_by_member=inviter)
    return 201, _invitation_out(invitation)


@tenant_router.get("/invitations", response=InvitationListResponse)
def list_invitations(request, cursor: str = None, limit: int = 50):
    """This tenant's invitations (pending, accepted, and revoked), newest first
    (Admin only)."""
    require_role(request, ADMIN)
    invitations, next_cursor, has_more = paginate(
        Invitation.objects.filter(tenant=request.auth.tenant), cursor, limit)
    return {"data": [_invitation_out(i) for i in invitations],
            "next_cursor": next_cursor, "has_more": has_more}


@tenant_router.delete(
    "/invitations/{invitation_id}",
    response={200: dict, 403: ProblemOut, 404: ProblemOut, 409: ProblemOut},
)
def revoke_invitation(request, invitation_id: UUID):
    """Revoke a still-pending invitation (Admin only). Idempotent on an
    already-revoked invite; 409 if it was already accepted (removing an active
    member is identity build 2)."""
    require_role(request, ADMIN)
    invitation = membership_services.revoke_invitation(
        request.auth.tenant, invitation_id)
    return 200, {"id": str(invitation.id), "status": invitation.status}


@tenant_router.get("/members", response=MemberListResponse)
def list_members(request, cursor: str = None, limit: int = 50):
    """This tenant's members (pending and active), newest first. Read floor —
    any tenant principal may list the roster."""
    require_role(request, READ)
    members, next_cursor, has_more = paginate(
        Member.objects.filter(tenant=request.auth.tenant), cursor, limit)
    return {"data": [_member_out(m) for m in members],
            "next_cursor": next_cursor, "has_more": has_more}


# ---- Sandbox self-serve (F4.4) ----


@tenant_router.post("/sandbox", response={200: dict, 403: ProblemOut})
def create_sandbox(request):
    """Provision (or fetch) the sandbox sibling and mint a ubb_test_ API key.

    The RAW key is returned exactly once per call (each POST mints a fresh
    key — that is also the rotation path). 403 from a sandbox key: sandboxes
    cannot nest.
    """
    tenant = request.auth.tenant
    if tenant.is_sandbox:
        raise Problem("forbidden",
                      "sandbox tenants cannot create sandboxes (use the live key)")
    from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox
    sandbox = get_or_create_sandbox(tenant)
    _key_obj, raw_key = TenantApiKey.create_key(sandbox, label="sandbox", is_test=True)
    return 200, {
        "sandbox_tenant_id": str(sandbox.id),
        "api_key": raw_key,
    }


@tenant_router.get("/sandbox", response={200: dict, 403: ProblemOut})
def get_sandbox(request):
    """Sandbox status for the calling live tenant (exists, id, key prefixes)."""
    tenant = request.auth.tenant
    if tenant.is_sandbox:
        raise Problem("forbidden", "sandbox status is read with the live key")
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
    from apps.billing.gating.models import RiskConfig
    from apps.billing.queries import get_billing_config
    rc = RiskConfig.objects.filter(tenant=t).first()
    bc = get_billing_config(t.id)
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
        "arrival_signals_enabled": t.arrival_signals_enabled,
        "default_task_provider_cost_limit_micros":
            rc.default_task_provider_cost_limit_micros if rc else None,
        "min_balance_micros": bc.min_balance_micros,
        "default_task_floor_snapshot_micros":
            bc.default_task_floor_snapshot_micros,
        "soft_min_balance_micros": bc.soft_min_balance_micros,
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
    from apps.metering.pricing.models import Rate
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
    if Rate.objects.filter(tenant=t, valid_to__isnull=True).exists():
        return "active rate cards exist (cards are currency-pinned)"
    return None


@tenant_router.get("/config", response=TenantConfigOut)
def get_tenant_config(request):
    return _config_out(request.auth.tenant)


@tenant_router.patch("/config", response={200: TenantConfigOut, 409: ProblemOut, 422: ProblemOut})
def update_tenant_config(request, payload: TenantConfigIn):
    from django.core.exceptions import ValidationError
    from apps.metering.pricing.models import Rate
    from apps.platform.tenants.models import SUPPORTED_CURRENCIES
    t = request.auth.tenant
    new_currency = None
    if payload.default_currency is not None:
        new_currency = payload.default_currency.strip().lower()
        if new_currency not in SUPPORTED_CURRENCIES:
            raise Problem(
                "unsupported_currency",
                f"unsupported currency {new_currency!r}: only "
                "2-decimal currencies are supported (zero-decimal "
                "currencies like jpy/krw are rejected until the "
                "minor-unit helper lands); allowed: "
                f"{', '.join(sorted(SUPPORTED_CURRENCIES))}")
        if new_currency != (t.default_currency or "usd").lower():
            reason = _currency_locked_reason(t)
            if reason is not None:
                raise Problem(
                    "currency_locked",
                    "default_currency cannot change once money "
                    f"exists for this tenant ({reason}); existing "
                    "wallets, Stripe Prices and invoices are "
                    "denominated in the current currency and there "
                    "is no FX/multi-currency support")
    if payload.require_cost_card_coverage is True and not t.require_cost_card_coverage:
        if not Rate.objects.filter(tenant=t, card_type="cost", valid_to__isnull=True).exists():
            raise Problem(
                "no_cost_cards",
                "require_cost_card_coverage cannot be enabled with zero "
                "active cost rate cards")
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
                raise Problem(
                    "stripe_tax_not_active",
                    f"Stripe Tax is not available on the connected account: {e}")
            status = getattr(tax_settings, "status", "")
            if status != "active":
                raise Problem(
                    "stripe_tax_not_active",
                    "Stripe Tax is not active on the connected "
                    f"account (status={status!r}); finish Stripe Tax "
                    "setup in the Stripe dashboard first")
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
    if payload.min_balance_micros is not None and payload.min_balance_micros < 0:
        raise Problem("invalid_config",
                      "min_balance_micros must be >= 0 (it is the "
                      "allowed overdraft magnitude, not a floor)")
    # Soft floor tenant default (#40, spec §F): negative is allowed (a
    # wind-down line above zero); the value may not exceed the tenant-default
    # hard floor's (that would put the wind-down line below the stop line).
    # When one PATCH sets both floors, the soft value validates against the
    # INCOMING hard, not the stored one (#52 — mirrors the billing-profile
    # PUT's effective_hard). Validated here, before any write, so a 422
    # leaves nothing partially applied.
    if ("soft_min_balance_micros" in fields_set
            and payload.soft_min_balance_micros is not None):
        from apps.billing.queries import get_billing_config
        effective_hard = payload.min_balance_micros
        if effective_hard is None:
            effective_hard = get_billing_config(t.id).min_balance_micros
        if payload.soft_min_balance_micros > effective_hard:
            raise Problem("invalid_config",
                          "soft_min_balance_micros must keep the soft line "
                          "at or above the hard floor's — the value cannot "
                          "exceed the effective tenant-default "
                          f"min_balance_micros ({effective_hard})")
    if ("default_task_provider_cost_limit_micros" in fields_set
            and payload.default_task_provider_cost_limit_micros is not None
            and payload.default_task_provider_cost_limit_micros <= 0):
        raise Problem("invalid_config",
                      "default_task_provider_cost_limit_micros must be "
                      "> 0, or null for no default")
    enforcement_changed = False
    if payload.enforcement_mode is not None:
        from apps.platform.tenants.models import ENFORCEMENT_MODE_CHOICES
        valid_modes = {c[0] for c in ENFORCEMENT_MODE_CHOICES}
        if payload.enforcement_mode not in valid_modes:
            raise Problem("invalid_config",
                          f"enforcement_mode must be one of {sorted(valid_modes)}")
        enforcement_changed = payload.enforcement_mode != t.enforcement_mode
        t.enforcement_mode = payload.enforcement_mode
    arrival_flipped = False
    if payload.arrival_signals_enabled is not None:
        arrival_flipped = payload.arrival_signals_enabled != t.arrival_signals_enabled
        t.arrival_signals_enabled = payload.arrival_signals_enabled
    try:
        t.save()
    except ValidationError as e:
        msg = "; ".join(
            f"{k}: {' '.join(str(x) for x in v)}" for k, v in e.message_dict.items()
        )
        raise Problem("invalid_config", msg)
    # The task-default limit lives on RiskConfig; write it only after the
    # tenant save succeeds. Created lazily so a tenant that sets only this
    # field gets a row.
    if "default_task_provider_cost_limit_micros" in fields_set:
        from apps.billing.gating.models import RiskConfig
        rc, _ = RiskConfig.objects.get_or_create(tenant=t)
        if (rc.default_task_provider_cost_limit_micros
                != payload.default_task_provider_cost_limit_micros):
            rc.default_task_provider_cost_limit_micros = (
                payload.default_task_provider_cost_limit_micros)
            rc.save(update_fields=["default_task_provider_cost_limit_micros",
                                   "updated_at"])
    # The tenant-default hard floor lives on BillingTenantConfig (#52) — the
    # row get_customer_min_balance reads, like its two siblings below. No
    # reconcile is kicked on change: floors are read fresh at detection time
    # and the hourly patrol re-aligns (same posture as the billing-profile PUT).
    if payload.min_balance_micros is not None:
        from apps.billing.queries import get_billing_config
        bc = get_billing_config(t.id)
        if bc.min_balance_micros != payload.min_balance_micros:
            bc.min_balance_micros = payload.min_balance_micros
            bc.save(update_fields=["min_balance_micros", "updated_at"])
    # The task-default floor snapshot lives on BillingTenantConfig (the row
    # RiskService reads at task creation).
    if "default_task_floor_snapshot_micros" in fields_set:
        from apps.billing.queries import get_billing_config
        bc = get_billing_config(t.id)
        if (bc.default_task_floor_snapshot_micros
                != payload.default_task_floor_snapshot_micros):
            bc.default_task_floor_snapshot_micros = (
                payload.default_task_floor_snapshot_micros)
            bc.save(update_fields=["default_task_floor_snapshot_micros",
                                   "updated_at"])
    # Soft floor tenant default (#40, spec §F) — lands on BillingTenantConfig
    # (the row get_customer_soft_min_balance reads). Validated against the
    # effective hard floor above, before any write.
    if "soft_min_balance_micros" in fields_set:
        from apps.billing.queries import get_billing_config
        bc = get_billing_config(t.id)
        if bc.soft_min_balance_micros != payload.soft_min_balance_micros:
            bc.soft_min_balance_micros = payload.soft_min_balance_micros
            bc.save(update_fields=["soft_min_balance_micros", "updated_at"])
    if enforcement_changed:
        # D17: clear stale Tier-2 keys so the new mode starts clean (esp. a
        # leftover stop flag that could wrongly suspend after a re-enable).
        from django.db import transaction
        from apps.billing.gating.services.live_ledger_service import LiveLedgerService
        transaction.on_commit(lambda: LiveLedgerService.cleanup_keys(t))
    if arrival_flipped:
        # Toggle choreography (#46, delivery spec §E): flipping either way
        # enqueues an immediate per-tenant reconcile — OFF→ON re-seeds honest
        # counters from durable truth within minutes; ON→OFF needs nothing
        # (outstanding holds drain at settle). Broker errors are swallowed:
        # the flip itself is already committed, and the hourly reconcile beat
        # is the guaranteed backstop for a lost enqueue.
        from django.db import transaction

        def _kick_reconcile(tenant_id=str(t.id)):
            import logging
            from apps.billing.gating.tasks import reconcile_tenant_live_counters
            try:
                reconcile_tenant_live_counters.delay(tenant_id)
            except Exception:
                logging.getLogger("ubb.billing").warning(
                    "arrival_signals.toggle_reconcile_enqueue_failed",
                    extra={"data": {"tenant_id": tenant_id}})

        transaction.on_commit(_kick_reconcile)
    return 200, _config_out(t)
