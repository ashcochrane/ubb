import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Sum, Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import NinjaAPI
from ninja.errors import HttpError

from api.v1.pagination import apply_cursor_filter, encode_cursor
from apps.platform.customers.models import Customer
from apps.referrals.api.schemas import (
    ProgramCreateRequest,
    ProgramUpdateRequest,
    ProgramOut,
    RegisterReferrerRequest,
    ReferrerOut,
    AttributeRequest,
    AttributeResponse,
    EarningsOut,
    ReferralOut,
    LedgerEntryOut,
    AnalyticsSummaryOut,
    AnalyticsEarningsOut,
    ReferrerEarningsSummary,
)
from apps.referrals.models import ReferralProgram, Referrer, Referral
from apps.referrals.rewards.models import ReferralRewardAccumulator, ReferralRewardLedger
from core.auth import ApiKeyAuth, ProductAccess

referrals_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_referrals_v1")

_product_check = ProductAccess("referrals")

logger = logging.getLogger(__name__)


def _program_to_dict(program):
    return {
        "id": str(program.id),
        "reward_type": program.reward_type,
        "reward_value": float(program.reward_value),
        "attribution_window_days": program.attribution_window_days,
        "reward_window_days": program.reward_window_days,
        "max_reward_micros": program.max_reward_micros,
        "estimated_cost_percentage": (
            float(program.estimated_cost_percentage)
            if program.estimated_cost_percentage is not None
            else None
        ),
        "status": program.status,
        "created_at": program.created_at.isoformat(),
        "updated_at": program.updated_at.isoformat(),
    }


# ---------- Program Management ----------


@referrals_api.post("/program", response=ProgramOut)
def create_program(request, payload: ProgramCreateRequest):
    _product_check(request)
    tenant = request.auth.tenant

    if ReferralProgram.objects.filter(tenant=tenant).exclude(status="deactivated").exists():
        raise HttpError(409, "Tenant already has an active or paused referral program")

    program = ReferralProgram.objects.create(
        tenant=tenant,
        reward_type=payload.reward_type,
        reward_value=payload.reward_value,
        attribution_window_days=payload.attribution_window_days,
        reward_window_days=payload.reward_window_days,
        max_reward_micros=payload.max_reward_micros,
        estimated_cost_percentage=payload.estimated_cost_percentage,
    )
    return _program_to_dict(program)


@referrals_api.get("/program", response=ProgramOut)
def get_program(request):
    _product_check(request)
    tenant = request.auth.tenant

    program = ReferralProgram.objects.filter(
        tenant=tenant,
    ).exclude(status="deactivated").order_by("-created_at").first()

    if not program:
        raise HttpError(404, "No active referral program found")

    return _program_to_dict(program)


@referrals_api.patch("/program", response=ProgramOut)
def update_program(request, payload: ProgramUpdateRequest):
    _product_check(request)
    tenant = request.auth.tenant

    program = ReferralProgram.objects.filter(
        tenant=tenant,
    ).exclude(status="deactivated").order_by("-created_at").first()

    if not program:
        raise HttpError(404, "No active referral program found")

    update_fields = ["updated_at"]
    for field_name in [
        "reward_type", "reward_value", "attribution_window_days",
        "reward_window_days", "max_reward_micros", "estimated_cost_percentage",
    ]:
        value = getattr(payload, field_name, None)
        if value is not None:
            setattr(program, field_name, value)
            update_fields.append(field_name)

    program.save(update_fields=update_fields)
    return _program_to_dict(program)


@referrals_api.delete("/program")
def deactivate_program(request):
    _product_check(request)
    tenant = request.auth.tenant

    program = ReferralProgram.objects.filter(
        tenant=tenant,
    ).exclude(status="deactivated").order_by("-created_at").first()

    if not program:
        raise HttpError(404, "No active referral program found")

    program.status = "deactivated"
    program.save(update_fields=["status", "updated_at"])
    return {"status": "deactivated"}


@referrals_api.post("/program/reactivate", response=ProgramOut)
def reactivate_program(request):
    _product_check(request)
    tenant = request.auth.tenant

    program = ReferralProgram.objects.filter(
        tenant=tenant, status="deactivated",
    ).order_by("-created_at").first()

    if not program:
        raise HttpError(404, "No deactivated referral program found")

    program.status = "active"
    program.save(update_fields=["status", "updated_at"])
    return _program_to_dict(program)


# ---------- Referrer Management ----------


@referrals_api.post("/referrers", response=ReferrerOut)
def register_referrer(request, payload: RegisterReferrerRequest):
    _product_check(request)
    tenant = request.auth.tenant

    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=tenant)

    if Referrer.objects.filter(customer=customer).exists():
        raise HttpError(409, "Customer is already registered as a referrer")

    # Check program exists
    if not ReferralProgram.objects.filter(tenant=tenant, status="active").exists():
        raise HttpError(400, "No active referral program. Create a program first.")

    referrer = Referrer.objects.create(tenant=tenant, customer=customer)

    return {
        "id": str(referrer.id),
        "customer_id": str(referrer.customer_id),
        "referral_code": referrer.referral_code,
        "referral_link_token": referrer.referral_link_token,
        "is_active": referrer.is_active,
        "created_at": referrer.created_at.isoformat(),
    }


@referrals_api.get("/referrers/{customer_id}", response=ReferrerOut)
def get_referrer(request, customer_id: str):
    _product_check(request)
    tenant = request.auth.tenant

    customer = get_object_or_404(Customer, id=customer_id, tenant=tenant)
    referrer = get_object_or_404(Referrer, customer=customer, tenant=tenant)

    return {
        "id": str(referrer.id),
        "customer_id": str(referrer.customer_id),
        "referral_code": referrer.referral_code,
        "referral_link_token": referrer.referral_link_token,
        "is_active": referrer.is_active,
        "created_at": referrer.created_at.isoformat(),
    }


@referrals_api.get("/referrers")
def list_referrers(request, cursor: str = None, limit: int = 50):
    _product_check(request)
    tenant = request.auth.tenant
    limit = min(max(limit, 1), 100)

    qs = Referrer.objects.filter(tenant=tenant).order_by("-created_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            raise HttpError(400, "Invalid cursor")

    referrers = list(qs[: limit + 1])
    has_more = len(referrers) > limit
    referrers = referrers[:limit]

    next_cursor = None
    if has_more and referrers:
        last = referrers[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [
            {
                "id": str(r.id),
                "customer_id": str(r.customer_id),
                "referral_code": r.referral_code,
                "referral_link_token": r.referral_link_token,
                "is_active": r.is_active,
                "created_at": r.created_at.isoformat(),
            }
            for r in referrers
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


# ---------- Attribution ----------


@referrals_api.post("/attribute", response=AttributeResponse)
def attribute_referral(request, payload: AttributeRequest):
    _product_check(request)
    tenant = request.auth.tenant

    if not payload.code and not payload.link_token:
        raise HttpError(400, "Either code or link_token is required")

    # Find the referrer
    if payload.code:
        referrer = Referrer.objects.filter(
            referral_code=payload.code, tenant=tenant, is_active=True,
        ).first()
    else:
        referrer = Referrer.objects.filter(
            referral_link_token=payload.link_token, tenant=tenant, is_active=True,
        ).first()

    if not referrer:
        raise HttpError(404, "Referrer not found or inactive")

    # Validate referred customer
    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=tenant)

    # Can't refer yourself
    if customer.id == referrer.customer_id:
        raise HttpError(400, "A customer cannot refer themselves")

    # Check not already referred
    if Referral.objects.filter(tenant=tenant, referred_customer=customer).exists():
        raise HttpError(409, "Customer has already been referred")

    # Get active program
    program = ReferralProgram.objects.filter(
        tenant=tenant, status="active",
    ).first()
    if not program:
        raise HttpError(400, "No active referral program")

    # For link attribution, check window
    if payload.link_token:
        # Link tokens are valid within attribution_window_days of referrer creation
        window_end = referrer.created_at + timedelta(days=program.attribution_window_days)
        if timezone.now() > window_end:
            raise HttpError(410, "Attribution window has expired")

    # Calculate reward window end
    reward_window_ends_at = None
    if program.reward_window_days:
        reward_window_ends_at = timezone.now() + timedelta(days=program.reward_window_days)

    with transaction.atomic():
        referral = Referral.objects.create(
            tenant=tenant,
            referrer=referrer,
            referred_customer=customer,
            referral_code_used=payload.code or payload.link_token,
            reward_window_ends_at=reward_window_ends_at,
            # Snapshot program config
            snapshot_reward_type=program.reward_type,
            snapshot_reward_value=program.reward_value,
            snapshot_max_reward_micros=program.max_reward_micros,
            snapshot_estimated_cost_percentage=program.estimated_cost_percentage,
        )

        # Create accumulator
        ReferralRewardAccumulator.objects.create(referral=referral)

        # Write outbox event
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import ReferralCreated

        write_event(ReferralCreated(
            tenant_id=str(tenant.id),
            referral_id=str(referral.id),
            referrer_id=str(referrer.id),
            referred_customer_id=str(customer.id),
        ))

    return {
        "referral_id": str(referral.id),
        "referrer_id": str(referrer.id),
        "referred_customer_id": str(customer.id),
        "status": referral.status,
    }


# ---------- Reward Data ----------


@referrals_api.get("/referrers/{customer_id}/earnings", response=EarningsOut)
def get_referrer_earnings(request, customer_id: str):
    _product_check(request)
    tenant = request.auth.tenant

    customer = get_object_or_404(Customer, id=customer_id, tenant=tenant)
    referrer = get_object_or_404(Referrer, customer=customer, tenant=tenant)

    referrals = Referral.objects.filter(referrer=referrer)
    totals = ReferralRewardAccumulator.objects.filter(
        referral__referrer=referrer,
    ).aggregate(
        total_earned=Sum("total_earned_micros"),
        total_spend=Sum("total_referred_spend_micros"),
    )

    return {
        "referrer_customer_id": str(customer.id),
        "total_earned_micros": totals["total_earned"] or 0,
        "total_referred_spend_micros": totals["total_spend"] or 0,
        "total_referrals": referrals.count(),
        "active_referrals": referrals.filter(status="active").count(),
    }


@referrals_api.get("/referrers/{customer_id}/referrals")
def get_referrer_referrals(request, customer_id: str, cursor: str = None, limit: int = 50):
    _product_check(request)
    tenant = request.auth.tenant
    limit = min(max(limit, 1), 100)

    customer = get_object_or_404(Customer, id=customer_id, tenant=tenant)
    referrer = get_object_or_404(Referrer, customer=customer, tenant=tenant)

    qs = Referral.objects.filter(
        referrer=referrer,
    ).select_related("referred_customer").order_by("-attributed_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="attributed_at")
        except ValueError:
            raise HttpError(400, "Invalid cursor")

    referrals = list(qs[: limit + 1])
    has_more = len(referrals) > limit
    referrals = referrals[:limit]

    next_cursor = None
    if has_more and referrals:
        last = referrals[-1]
        next_cursor = encode_cursor(last.attributed_at, last.id)

    data = []
    for ref in referrals:
        try:
            acc = ref.reward_accumulator
            earned = acc.total_earned_micros
            spend = acc.total_referred_spend_micros
        except ReferralRewardAccumulator.DoesNotExist:
            earned = 0
            spend = 0

        data.append({
            "id": str(ref.id),
            "referred_customer_id": str(ref.referred_customer_id),
            "referred_external_id": ref.referred_customer.external_id,
            "referral_code_used": ref.referral_code_used,
            "status": ref.status,
            "reward_type": ref.snapshot_reward_type,
            "total_earned_micros": earned,
            "total_referred_spend_micros": spend,
            "attributed_at": ref.attributed_at.isoformat(),
            "reward_window_ends_at": (
                ref.reward_window_ends_at.isoformat()
                if ref.reward_window_ends_at
                else None
            ),
        })

    return {
        "data": data,
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@referrals_api.get("/referrals/{referral_id}/ledger")
def get_referral_ledger(request, referral_id: str, cursor: str = None, limit: int = 50):
    _product_check(request)
    tenant = request.auth.tenant
    limit = min(max(limit, 1), 100)

    referral = get_object_or_404(Referral, id=referral_id, tenant=tenant)

    qs = ReferralRewardLedger.objects.filter(
        referral=referral,
    ).order_by("-period_start", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            raise HttpError(400, "Invalid cursor")

    entries = list(qs[: limit + 1])
    has_more = len(entries) > limit
    entries = entries[:limit]

    next_cursor = None
    if has_more and entries:
        last = entries[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [
            {
                "id": str(e.id),
                "period_start": e.period_start.isoformat(),
                "period_end": e.period_end.isoformat(),
                "referred_spend_micros": e.referred_spend_micros,
                "raw_cost_micros": e.raw_cost_micros,
                "reward_micros": e.reward_micros,
                "calculation_method": e.calculation_method,
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


# ---------- Revocation ----------


@referrals_api.delete("/referrals/{referral_id}")
def revoke_referral(request, referral_id: str):
    _product_check(request)
    tenant = request.auth.tenant

    referral = get_object_or_404(Referral, id=referral_id, tenant=tenant)

    if referral.status == "revoked":
        raise HttpError(409, "Referral is already revoked")

    referral.status = "revoked"
    referral.save(update_fields=["status", "updated_at"])
    return {"status": "revoked"}


# ---------- Payout Export ----------


@referrals_api.get("/payouts/export")
def payout_export(request):
    _product_check(request)
    tenant = request.auth.tenant

    referrers = Referrer.objects.filter(tenant=tenant).select_related("customer")

    data = []
    total_payout = 0

    for referrer in referrers:
        acc_totals = ReferralRewardAccumulator.objects.filter(
            referral__referrer=referrer,
        ).aggregate(
            earned=Sum("total_earned_micros"),
            spend=Sum("total_referred_spend_micros"),
        )
        earned = acc_totals["earned"] or 0
        if earned <= 0:
            continue

        ref_count = Referral.objects.filter(referrer=referrer).count()
        active_count = Referral.objects.filter(referrer=referrer, status="active").count()

        data.append({
            "referrer_customer_id": str(referrer.customer_id),
            "external_id": referrer.customer.external_id,
            "referral_code": referrer.referral_code,
            "total_earned_micros": earned,
            "total_referred_spend_micros": acc_totals["spend"] or 0,
            "referral_count": ref_count,
            "active_referral_count": active_count,
        })
        total_payout += earned

    return {
        "data": data,
        "total_payout_micros": total_payout,
        "referrer_count": len(data),
        "exported_at": timezone.now().isoformat(),
    }


# ---------- Analytics ----------


@referrals_api.get("/analytics/summary", response=AnalyticsSummaryOut)
def analytics_summary(request):
    _product_check(request)
    tenant = request.auth.tenant

    total_referrers = Referrer.objects.filter(tenant=tenant).count()
    referrals_qs = Referral.objects.filter(tenant=tenant)
    total_referrals = referrals_qs.count()
    active_referrals = referrals_qs.filter(status="active").count()

    totals = ReferralRewardAccumulator.objects.filter(
        referral__tenant=tenant,
    ).aggregate(
        total_earned=Sum("total_earned_micros"),
        total_spend=Sum("total_referred_spend_micros"),
    )

    return {
        "total_referrers": total_referrers,
        "total_referrals": total_referrals,
        "active_referrals": active_referrals,
        "total_rewards_earned_micros": totals["total_earned"] or 0,
        "total_referred_spend_micros": totals["total_spend"] or 0,
    }


@referrals_api.get("/analytics/earnings")
def analytics_earnings(request, period_start: str = None, period_end: str = None):
    _product_check(request)
    tenant = request.auth.tenant

    referrers = Referrer.objects.filter(
        tenant=tenant,
    ).select_related("customer")

    referrer_data = []
    total_earned = 0

    for referrer in referrers:
        acc_totals = ReferralRewardAccumulator.objects.filter(
            referral__referrer=referrer,
        ).aggregate(
            earned=Sum("total_earned_micros"),
        )
        earned = acc_totals["earned"] or 0
        ref_count = Referral.objects.filter(referrer=referrer).count()

        if earned > 0 or ref_count > 0:
            referrer_data.append({
                "referrer_customer_id": str(referrer.customer_id),
                "external_id": referrer.customer.external_id,
                "referral_code": referrer.referral_code,
                "total_earned_micros": earned,
                "referral_count": ref_count,
            })
            total_earned += earned

    today = timezone.now().date()
    return {
        "period_start": period_start or today.replace(day=1).isoformat(),
        "period_end": period_end or today.isoformat(),
        "referrers": referrer_data,
        "total_earned_micros": total_earned,
    }
