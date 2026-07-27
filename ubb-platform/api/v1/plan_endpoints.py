"""The plans surface — /api/v1/plans.

Plans are a KERNEL concept (design doc 2026-07-27): a plan's fee axes are
realized by subscriptions via Stripe, its markup axis by metering at rating
time, and neither product owns it. The router lives in the composition layer,
which may import any product.

Gated on ProductAccess("billing"): a plan is a commercial offer, and charging
for one is what the billing product is.
"""
from django.db import IntegrityError, transaction
from ninja import Router

from api.v1.schemas import AssignPlanIn, PlanIn, PlanListOut, PlanOut, PlanUpdateIn
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
from apps.platform.customers.models import Customer
from apps.platform.plans import queries
from apps.platform.plans.models import Plan
from apps.platform.plans.services import PlanInUse, PlanService
from core.auth import ADMIN, ApiKeyAuth, ProductAccess, READ, WRITE, role_floor
from core.problems import Problem, ProblemOut

plan_router = Router(auth=ApiKeyAuth())

_product_check = ProductAccess("billing")


def _plan_out(plan):
    return {
        "id": str(plan.id),
        "key": plan.key,
        "name": plan.name,
        "access_fee_micros": plan.access_fee_micros,
        "per_seat_micros": plan.per_seat_micros,
        "markup_percentage_micros": plan.markup_percentage_micros,
        "fixed_uplift_micros": plan.fixed_uplift_micros,
        "interval": plan.interval,
        "pricing_version": plan.pricing_version,
        "archived_at": plan.archived_at.isoformat() if plan.archived_at else None,
    }


@plan_router.get("/plans", response={200: PlanListOut})
@role_floor(READ)
def list_plans(request, include_archived: bool = False):
    _product_check(request)
    plans = queries.list_plans(request.auth.tenant.id, include_archived=include_archived)
    return 200, {"plans": [_plan_out(p) for p in plans]}


@plan_router.get("/plans/{key}", response={200: PlanOut, 404: ProblemOut})
@role_floor(READ)
def get_plan(request, key: str):
    _product_check(request)
    plan = queries.get_plan_by_key(request.auth.tenant.id, key)
    if plan is None:
        raise Problem("not_found", f"plan with key '{key}' not found")
    return 200, _plan_out(plan)


@plan_router.post("/plans", response={201: PlanOut, 409: ProblemOut})
@role_floor(ADMIN)
@records_audit("plan.created")
def create_plan(request, payload: PlanIn):
    _product_check(request)
    tenant = request.auth.tenant
    try:
        with transaction.atomic():
            plan = Plan.objects.create(
                tenant=tenant, key=payload.key, name=payload.name,
                access_fee_micros=payload.access_fee_micros,
                per_seat_micros=payload.per_seat_micros,
                markup_percentage_micros=payload.markup_percentage_micros,
                fixed_uplift_micros=payload.fixed_uplift_micros,
                interval=payload.interval,
            )
            audit_record(
                action="plan.created", tenant_id=tenant.id,
                resource_type="plan", resource_id=plan.key,
                metadata=_plan_out(plan))
    except IntegrityError:
        raise Problem("conflict", f"plan with key '{payload.key}' already exists")
    return 201, _plan_out(plan)


@plan_router.patch("/plans/{key}", response={200: PlanOut, 404: ProblemOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("plan.updated")
def update_plan(request, key: str, payload: PlanUpdateIn):
    """Edit a plan.

    The two axis families reprice differently, deliberately:
      - FEE axes are grandfathered. Stripe Prices are immutable, so a fee edit
        mints a new versioned Price and existing subscribers keep the old one
        unless migrate_existing=true.
      - MARKUP is live. It has no Stripe object, so an edit applies to the next
        rated event for every customer on the plan.

    Trials and coupons are deliberate non-goals: Stripe owns those levers.
    """
    from apps.subscriptions.orchestration.service import (
        OrchestrationError, SubscriptionOrchestrator,
    )
    from core.exceptions import StripeFatalError

    _product_check(request)
    tenant = request.auth.tenant
    plan = queries.get_plan_by_key(tenant.id, key)
    if plan is None:
        raise Problem("not_found", f"plan with key '{key}' not found")

    # Markup and name are UBB-side: a plain write, no Stripe involvement.
    # Committed AND audited together, in their own transaction, before the
    # fee branch runs. This axis's fate must never depend on what the fee
    # branch's external Stripe call does next: a fee-branch failure below
    # must not silently drop this already-durable change from the audit
    # trail (Finding 1), and an empty payload must record nothing (Finding 2).
    fields = []
    if payload.name is not None:
        plan.name = payload.name
        fields.append("name")
    if payload.markup_percentage_micros is not None:
        plan.markup_percentage_micros = payload.markup_percentage_micros
        fields.append("markup_percentage_micros")
    if payload.fixed_uplift_micros is not None:
        plan.fixed_uplift_micros = payload.fixed_uplift_micros
        fields.append("fixed_uplift_micros")
    if fields:
        with transaction.atomic():
            # Full save(), not update_fields only — the save hook bumps the
            # markup cache version, and a re-priced plan must take effect
            # immediately.
            plan.save()
            audit_record(
                action="plan.updated", tenant_id=tenant.id,
                resource_type="plan", resource_id=plan.key,
                metadata={"changed": fields, **_plan_out(plan)})

    # Fee axes go through the orchestrator, which mints versioned Stripe
    # Prices — an external call, so it stays outside any DB transaction: a
    # transaction can't be held open across a Stripe round-trip. Audited only
    # on success — a failure here commits nothing on this axis, so there is
    # nothing to audit, and it must not retroactively touch the markup/name
    # audit entry recorded above.
    if payload.access_fee_micros is not None or payload.per_seat_micros is not None:
        try:
            plan = SubscriptionOrchestrator.update_plan_prices(
                tenant, key,
                access_fee_micros=payload.access_fee_micros,
                per_seat_micros=payload.per_seat_micros,
                migrate_existing=payload.migrate_existing)
        except (OrchestrationError, StripeFatalError) as e:
            raise Problem("validation_error", str(e))
        audit_record(
            action="plan.updated", tenant_id=tenant.id,
            resource_type="plan", resource_id=plan.key,
            metadata={"changed": ["access_fee_micros", "per_seat_micros"],
                      "migrate_existing": payload.migrate_existing, **_plan_out(plan)})

    return 200, _plan_out(plan)


@plan_router.delete("/plans/{key}", response={204: None, 404: ProblemOut, 409: ProblemOut})
@role_floor(ADMIN)
@records_audit("plan.archived")
def archive_plan(request, key: str):
    """Archive a plan. Refused while customers are still assigned — archiving
    an assigned plan would silently drop their markup to the tenant default."""
    _product_check(request)
    tenant = request.auth.tenant
    plan = queries.get_plan_by_key(tenant.id, key)
    if plan is None:
        raise Problem("not_found", f"plan with key '{key}' not found")
    try:
        # PlanService.archive is a pure-DB operation (no Stripe call), so the
        # mutation and its audit entry commit — or roll back — together.
        with transaction.atomic():
            PlanService.archive(plan)
            audit_record(
                action="plan.archived", tenant_id=tenant.id,
                resource_type="plan", resource_id=plan.key, metadata={"key": plan.key})
    except PlanInUse as e:
        raise Problem("conflict", str(e))
    return 204, None


@plan_router.post("/customers/{external_id}/plan",
                  response={200: dict, 404: ProblemOut})
@role_floor(WRITE)
@records_audit("plan.assigned")
def assign_plan(request, external_id: str, payload: AssignPlanIn):
    """Put a customer on a plan.

    This is the plan-membership write and it never touches Stripe. Starting the
    Stripe subscription for a plan's fee axes is a separate call
    (POST /subscriptions/customers/{external_id}/subscribe), because a
    markup-only plan has no Stripe subscription to start.
    """
    _product_check(request)
    tenant = request.auth.tenant
    customer = Customer.objects.filter(tenant=tenant, external_id=external_id).first()
    if customer is None:
        raise Problem("not_found", "customer not found")
    plan = queries.get_plan_by_key(tenant.id, payload.plan_key)
    if plan is None or plan.archived_at is not None:
        raise Problem("not_found", f"plan with key '{payload.plan_key}' not found")
    # PlanService.assign is a pure-DB operation (no Stripe call), so the
    # mutation and its audit entry commit — or roll back — together.
    with transaction.atomic():
        PlanService.assign(tenant, customer, plan)
        audit_record(
            action="plan.assigned", tenant_id=tenant.id,
            resource_type="customer", resource_id=customer.external_id,
            metadata={"external_id": customer.external_id, "plan_key": plan.key})
    return 200, {"external_id": customer.external_id, "plan_key": plan.key}
