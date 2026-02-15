from django.db import IntegrityError
from ninja import NinjaAPI, Schema

from core.auth import ApiKeyAuth
from apps.platform.customers.models import Customer


class CreateCustomerRequest(Schema):
    external_id: str
    stripe_customer_id: str = ""
    metadata: dict = {}


class CustomerResponse(Schema):
    id: str
    external_id: str
    stripe_customer_id: str
    status: str


platform_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_platform_v1")


@platform_api.post("/customers", response={201: CustomerResponse, 409: dict})
def create_customer(request, payload: CreateCustomerRequest):
    try:
        customer = Customer.objects.create(
            tenant=request.auth.tenant,
            external_id=payload.external_id,
            stripe_customer_id=payload.stripe_customer_id,
            metadata=payload.metadata,
        )
        return 201, {
            "id": str(customer.id),
            "external_id": customer.external_id,
            "stripe_customer_id": customer.stripe_customer_id,
            "status": customer.status,
        }
    except IntegrityError:
        return 409, {"error": "Customer with this external_id already exists"}
