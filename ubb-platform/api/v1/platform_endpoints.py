from django.db import IntegrityError
from ninja import Router, Schema

from core.auth import ApiKeyAuth, READ, WRITE, role_floor
from core.problems import Problem, ProblemOut
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
from apps.platform.customers.models import Customer


class CreateCustomerRequest(Schema):
    external_id: str
    stripe_customer_id: str = ""
    metadata: dict = {}
    account_type: str = "individual"
    parent_external_id: str = ""
    billing_topology: str = ""


class CustomerResponse(Schema):
    id: str
    external_id: str
    stripe_customer_id: str
    status: str


platform_router = Router(auth=ApiKeyAuth())


@platform_router.post("/customers", response={201: CustomerResponse, 409: ProblemOut, 422: ProblemOut})
@role_floor(WRITE)
@records_audit("customer.created")
def create_customer(request, payload: CreateCustomerRequest):
    tenant = request.auth.tenant
    at = payload.account_type or "individual"
    if at not in ("individual", "business", "seat"):
        raise Problem("validation_error", f"invalid account_type {at}")
    parent = None
    topology = ""
    if at == "seat":
        if not payload.parent_external_id:
            raise Problem("validation_error", "seat requires parent_external_id")
        parent = Customer.objects.filter(
            tenant=tenant, external_id=payload.parent_external_id, account_type="business"
        ).first()
        if parent is None:
            raise Problem("validation_error", "parent business not found")
    elif at == "business":
        if payload.billing_topology not in ("pooled", "allocated"):
            raise Problem("validation_error",
                          "business requires billing_topology pooled|allocated")
        topology = payload.billing_topology
    try:
        from django.db import transaction
        with transaction.atomic():
            customer = Customer.objects.create(
                tenant=tenant,
                external_id=payload.external_id,
                stripe_customer_id=payload.stripe_customer_id,
                metadata=payload.metadata,
                account_type=at,
                parent=parent,
                billing_topology=topology,
            )
            # Roster grew: push the new live seat count to Stripe on commit so the
            # subscription's per-seat quantity stays in lock-step with the roster.
            if at == "seat" and parent is not None:
                from apps.subscriptions.orchestration.seats import sync_seat_quantity_on_commit
                sync_seat_quantity_on_commit(parent)
            # Audit the new customer in the same transaction (ADR-004).
            audit_record(
                action="customer.created", tenant_id=tenant.id,
                resource_type="customer", resource_id=customer.id,
                metadata={"external_id": customer.external_id,
                          "account_type": at,
                          "billing_topology": topology,
                          "parent_external_id": payload.parent_external_id})
        return 201, {
            "id": str(customer.id),
            "external_id": customer.external_id,
            "stripe_customer_id": customer.stripe_customer_id,
            "status": customer.status,
        }
    except IntegrityError:
        raise Problem("conflict", "customer with this external_id already exists")


@platform_router.get("/accounts/business/{external_id}", response={200: dict, 404: ProblemOut})
@role_floor(READ)
def get_business(request, external_id: str):
    from apps.billing.wallets.models import Wallet

    biz = Customer.objects.filter(
        tenant=request.auth.tenant, external_id=external_id, account_type="business"
    ).first()
    if biz is None:
        raise Problem("not_found", "business not found")
    pooled_balance = None
    if biz.billing_topology == "pooled":
        w = Wallet.objects.filter(customer=biz).first()
        pooled_balance = w.balance_micros if w else 0
    seats = [
        {"external_id": s.external_id, "id": str(s.id), "status": s.status}
        for s in biz.seats.all().order_by("external_id")
    ]
    return 200, {
        "external_id": biz.external_id,
        "id": str(biz.id),
        "billing_topology": biz.billing_topology,
        "pooled_balance_micros": pooled_balance,
        "seats": seats,
    }

