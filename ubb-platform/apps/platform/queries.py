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
- apps/subscriptions/stripe/sync.py -> get_tenant_stripe_account()
- apps/subscriptions/stripe/binding.py -> get_stripe_customer_holders()
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


def get_stripe_customer_holders(connected_account_id, *, livemode,
                                stripe_customer_id) -> list[dict[str, str]]:
    """EVERY live customer holding one Stripe customer id, in one Stripe namespace.

    The namespace is the connected account plus the mode: a customer counts
    when it is not soft-deleted, its ``stripe_customer_id`` equals
    ``stripe_customer_id``, and its tenant holds ``connected_account_id`` in
    the matching mode (a live tenant for ``livemode=True``, a sandbox for
    ``False``). Several tenants may hold one account, and nothing makes a
    Stripe customer id unique, so this can answer more than one holder.

    It answers ALL of them, as ``[{"customer_id": ..., "tenant_id": ...}]``,
    and never chooses one (R10 Stage C4, PLAN §7 item 33). The dict this
    replaced, keyed on the Stripe id, kept whichever duplicate the query plan
    returned last, and the subscription sync then bound mirrors to it. A
    caller that needs one customer must treat any count but one as no answer.
    The list is sorted by customer id so logs read the same on every pass; the
    order is never an identity.
    """
    from apps.platform.customers.models import Customer

    if not (connected_account_id and stripe_customer_id):
        return []
    rows = Customer.objects.filter(
        stripe_customer_id=stripe_customer_id,
        tenant__stripe_connected_account_id=connected_account_id,
        tenant__is_sandbox=not livemode,
    ).values_list("id", "tenant_id")
    return sorted(({"customer_id": str(customer_id), "tenant_id": str(tenant_id)}
                   for customer_id, tenant_id in rows),
                  key=lambda holder: holder["customer_id"])
