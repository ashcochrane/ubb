from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from core.auth import ApiKeyAuth, READ, WRITE, role_floor
from core.identifiers import UUIDIdentifier
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


class CustomerIdentityOut(Schema):
    """Who a customer IS, by the identity UBB assigned them.

    ⚠ **THIS ROUTE EXISTS BECAUSE #501 TOOK AWAY THE ONLY READ THAT ANSWERED
    IT**, and that is worth stating on a slice whose whole subject is removing
    published surface. One customer's margin used to publish `external_id`
    beside its figures, and that was the single place a caller holding UBB's
    identity for a customer could learn the tenant's own word for them. The one
    economic query groups by IDENTITY and publishes no external id — rightly: a
    tenant's own vocabulary is not a measure, and a report is not a directory.
    So the capability was never the report's, and it is here, on the mount that
    owns customers.

    It matters beyond a page title: the subscription lifecycle is keyed on the
    external id (`/subscriptions/customers/{external_id}/...`) while every
    metering and billing read is keyed on the UUID, so a surface holding one and
    needing the other has nowhere else to turn.

    `account_type` and `parent_external_id` travel with it because a seat's
    bill is its business's, and a caller that had to ask a second question to
    find that out would be one round trip from rendering a seat as if it paid
    its own way.
    """

    id: str
    external_id: str
    account_type: str
    #: The business a seat belongs to, or "" for a customer that is not one.
    parent_external_id: str = ""
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


@platform_router.get("/customers/{customer_id}",
                     response={200: CustomerIdentityOut, 404: ProblemOut})
@role_floor(READ)
def get_customer(request, customer_id: UUIDIdentifier):
    """One customer's identity: who UBB knows them as, and who you call them.

    Read this where you hold UBB's id for a customer and need the id you gave
    them — the subscription lifecycle is addressed by your own external id while
    every metering and billing read is addressed by UBB's, and this is what
    bridges the two.

    It answers about identity and says nothing about money: what a customer cost
    or earned is one question asked at
    `GET /metering/analytics/economics`, filtered to them.
    """
    customer = get_object_or_404(Customer, id=customer_id,
                                 tenant=request.auth.tenant)
    return 200, {
        "id": str(customer.id),
        "external_id": customer.external_id,
        "account_type": customer.account_type,
        "parent_external_id": (customer.parent.external_id
                               if customer.parent_id else ""),
        "status": customer.status,
    }


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

