"""Tenant provisioning service.

Single entry point for creating a new tenant + tenant user + API key
for a Clerk-authenticated user. Called today from POST /platform/tenant;
later, also from a Clerk webhook handler.
"""
from django.db import IntegrityError, transaction

from apps.platform.events.outbox import write_event
from apps.platform.events.schemas import TenantProvisionedEvent
from apps.platform.tenants.models import Tenant, TenantApiKey, TenantUser
from core.clerk_api import get_clerk_user


def provision_tenant_for_clerk_user(
    clerk_user_id: str,
    tenant_name: str,
) -> tuple[Tenant, TenantUser, str | None]:
    """Create Tenant + TenantUser + TenantApiKey for a new Clerk user.

    Idempotent: if a TenantUser already exists for clerk_user_id,
    returns the existing tenant + tenant_user with raw_api_key=None.
    Keys are returned exactly once, at first creation.

    Raises ClerkAPIError if the email lookup fails.
    """
    existing = TenantUser.objects.select_related("tenant").filter(
        clerk_user_id=clerk_user_id
    ).first()
    if existing:
        return existing.tenant, existing, None

    clerk_user = get_clerk_user(clerk_user_id)

    try:
        with transaction.atomic():
            tenant = Tenant.objects.create(
                name=tenant_name,
                products=["metering"],
            )
            tenant_user = TenantUser.objects.create(
                tenant=tenant,
                clerk_user_id=clerk_user_id,
                email=clerk_user["email"],
                role="owner",
            )
            _, raw_key = TenantApiKey.create_key(tenant, label="default")
            write_event(TenantProvisionedEvent(
                tenant_id=str(tenant.id),
                clerk_user_id=clerk_user_id,
                mode="track",
            ))
    except IntegrityError:
        # Concurrent provisioning raced us — return the winner.
        tenant_user = TenantUser.objects.select_related("tenant").get(
            clerk_user_id=clerk_user_id
        )
        return tenant_user.tenant, tenant_user, None

    return tenant, tenant_user, raw_key
