"""The plans surface — /api/v1/plans.

Plans are a KERNEL concept (design doc 2026-07-27): a plan's fee axes are
realized by subscriptions via Stripe, its usage axis by metering at rating time
— from the Pricing Book the plan names — and neither product owns it. The
router lives in the composition layer, which may import any product.

Gated on ProductAccess("billing"): a plan is a commercial offer, and charging
for one is what the billing product is.
"""
from django.db import IntegrityError, transaction
from ninja import Router

from api.v1.schemas import AssignPlanIn, PlanIn, PlanListOut, PlanOut, PlanUpdateIn
from apps.metering.pricing.services.book_service import BookService
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
from apps.platform.customers.models import Customer
from apps.platform.plans import queries
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


def _the_new_plans_book(tenant, key, name):
    """The book this plan will price from, refusing one it may not adopt (#362).

    `the_book_a_plan_prices_from` will reuse a plain catalogue already keyed to
    match, and will NOT reuse a customer's override book or the tenant's
    provider default — neither is in the uniqueness key, so a book of either
    kind holding this key is refused by the database rather than adopted.

    That refusal arrives as an `IntegrityError` on the BOOK's uniqueness, and
    the caller's own handler reads an `IntegrityError` as *the plan key is
    taken* — which would be false and unactionable here. Answering it in its
    own savepoint is what keeps the two conflicts distinguishable.
    """
    try:
        with transaction.atomic():
            return BookService.the_book_a_plan_prices_from(
                tenant, plan_key=key, plan_name=name)
    except IntegrityError as exc:
        raise Problem(
            "conflict",
            f"a pricing book with key '{key}' already exists and is not one a "
            f"plan may price from — it belongs to one customer, or it is the "
            f"tenant's default book. Give the plan another key.") from exc


@plan_router.post("/plans", response={201: PlanOut, 409: ProblemOut})
@role_floor(ADMIN)
@records_audit("plan.created")
def create_plan(request, payload: PlanIn):
    _product_check(request)
    tenant = request.auth.tenant
    try:
        with transaction.atomic():
            # THE BOOK FIRST, AND THE ORDER IS THE POINT (#362, #151 §7.2).
            # A Plan names the Pricing Book its customers are priced from and
            # the column is NOT NULL, so there is no arrangement of these two
            # statements that writes the plan first: `PlanService.create` takes
            # the id, and the id does not exist until the line above has run.
            # The book arrives empty — UBB ships no catalogue — so this plan
            # prices nothing from it until the tenant publishes rules into it.
            #
            # NO AUDIT ACTION OF ITS OWN, on #361's precedent for the override
            # book: the container is bookkeeping and the PLAN is the act, so a
            # ledger reader counting two would be counting a decision nobody
            # took.
            book = _the_new_plans_book(tenant, payload.key, payload.name)
            plan = PlanService.create(
                tenant, pricing_book_id=book.id,
                key=payload.key, name=payload.name,
                access_fee_micros=payload.access_fee_micros,
                per_seat_micros=payload.per_seat_micros,
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

    FEE axes are grandfathered: Stripe Prices are immutable, so a fee edit
    mints a new versioned Price and existing subscribers keep the old one unless
    migrate_existing=true.

    What the plan's customers pay for usage is not edited here. It is the rules
    in the Pricing Book the plan names, changed through a publish on that book,
    which is what gives a tenant a diff to read before a price moves.

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

    # The name is UBB-side: a plain write, no Stripe involvement. Committed AND
    # audited in its own transaction, before the fee branch runs. Its fate must
    # never depend on what the fee branch's external Stripe call does next: a
    # fee-branch failure below must not silently drop this already-durable
    # change from the audit trail (Finding 1), and an empty payload must record
    # nothing (Finding 2). ⚠ It shared this branch with the plan's two markup
    # columns until #369, which is why one field still gets a list.
    fields = []
    if payload.name is not None:
        plan.name = payload.name
        fields.append("name")
    if fields:
        with transaction.atomic():
            plan.save()
            audit_record(
                action="plan.updated", tenant_id=tenant.id,
                resource_type="plan", resource_id=plan.key,
                metadata={"changed": fields, **_plan_out(plan)})

    # Fee axes go through the orchestrator, which mints versioned Stripe
    # Prices — an external call, so it stays outside any DB transaction: a
    # transaction can't be held open across a Stripe round-trip. Audited only
    # on success — a failure here commits nothing on this axis, so there is
    # nothing to audit, and it must not retroactively touch the name audit
    # entry recorded above.
    fee_fields = []
    if payload.access_fee_micros is not None:
        fee_fields.append("access_fee_micros")
    if payload.per_seat_micros is not None:
        fee_fields.append("per_seat_micros")
    if fee_fields:
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
            metadata={"changed": fee_fields,
                      "migrate_existing": payload.migrate_existing, **_plan_out(plan)})

    return 200, _plan_out(plan)


@plan_router.delete("/plans/{key}", response={204: None, 404: ProblemOut, 409: ProblemOut})
@role_floor(ADMIN)
@records_audit("plan.archived")
def archive_plan(request, key: str):
    """Archive a plan. Refused while customers are still assigned — archiving
    an assigned plan would silently move every one of them off the book it
    prices them from."""
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
    usage-only plan has no Stripe subscription to start.
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
