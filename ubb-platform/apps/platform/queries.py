"""Platform Query Interface — Cross-Product Read Contract.

This module provides the ONLY approved way for product modules
(billing, subscriptions) to read platform identity data like
Stripe account IDs. Functions return scalars or dicts, never
ORM instances.

If platform becomes a separate service, these functions become
HTTP calls. All callers remain untouched.

Consumers:
- apps/billing/connectors/stripe/stripe_api.py -> get_customer_stripe_id(), get_tenant_stripe_account()
- apps/billing/connectors/stripe/receipts.py -> get_customer_stripe_id(), get_tenant_stripe_account()
- apps/billing/connectors/stripe/tasks.py -> get_tenant_stripe_account()
- apps/billing/connectors/stripe/handlers.py -> get_tenant_stripe_account()
- apps/subscriptions/stripe/sync.py -> get_tenant_stripe_account(), get_customers_by_stripe_id()
- api/v1/billing_endpoints.py -> get_tenant_stripe_account(), get_customer_stripe_id()
- api/v1/me_endpoints.py -> get_tenant_stripe_account(), get_customer_stripe_id()
- api/v1/platform_endpoints.py -> get_customer_stripe_id()
"""
from typing import Optional


def get_tenant_stripe_account(tenant_id) -> Optional[str]:
    """Returns the tenant's Stripe connected account ID, or None if not set."""
    from apps.platform.tenants.models import Tenant

    value = Tenant.objects.filter(id=tenant_id).values_list(
        "stripe_connected_account_id", flat=True
    ).first()
    return value if value else None


def get_customer_stripe_id(customer_id) -> Optional[str]:
    """Returns the customer's Stripe customer ID, or None if not set."""
    from apps.platform.customers.models import Customer

    value = Customer.objects.filter(id=customer_id).values_list(
        "stripe_customer_id", flat=True
    ).first()
    return value if value else None


def get_customers_by_stripe_id(tenant_id) -> dict[str, str]:
    """Returns {stripe_customer_id: customer_id} for all customers with Stripe IDs.

    Used by subscription sync to match Stripe subscriptions to platform customers.
    """
    from apps.platform.customers.models import Customer

    return {
        stripe_id: str(cust_id)
        for cust_id, stripe_id in Customer.objects.filter(
            tenant_id=tenant_id,
            stripe_customer_id__gt="",
        ).values_list("id", "stripe_customer_id")
    }
