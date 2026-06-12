"""Sandbox provisioning (F4.4).

A sandbox is a per-tenant SIBLING Tenant row (is_sandbox=True,
parent_tenant=<live tenant>). Because ApiKeyAuth sets request.tenant from the
key's tenant and every domain model is tenant-scoped, a sandbox tenant gets
isolation, idempotency, rate limits and all beat jobs automatically.

The sandbox copies the live tenant's product/billing configuration shape but
NEVER any Stripe linkage: stripe_connected_account_id / stripe_customer_id /
charges_enabled stay at their blank defaults so a sandbox can only ever
complete TEST-mode Stripe connections.
"""
import logging

from django.db import IntegrityError, transaction

from apps.platform.tenants.models import Tenant

logger = logging.getLogger(__name__)


def get_or_create_sandbox(tenant):
    """Return the tenant's sandbox sibling, creating it on first use.

    Race-safe: a concurrent first-create loses on the
    uq_one_sandbox_per_parent partial unique and refetches the winner.
    Raises ValueError if called ON a sandbox (no sandboxes of sandboxes).
    """
    if tenant.is_sandbox:
        raise ValueError("cannot create a sandbox for a sandbox tenant")

    existing = Tenant.objects.filter(parent_tenant=tenant, is_sandbox=True).first()
    if existing is not None:
        return existing

    try:
        with transaction.atomic():
            sandbox = Tenant.objects.create(
                name=f"{tenant.name} (sandbox)",
                is_sandbox=True,
                parent_tenant=tenant,
                products=list(tenant.products or []),
                billing_mode=tenant.billing_mode,
                default_currency=tenant.default_currency,
                require_cost_card_coverage=tenant.require_cost_card_coverage,
                # NEVER copy Stripe fields: stripe_connected_account_id,
                # stripe_customer_id, charges_enabled stay blank/False.
            )
    except IntegrityError:
        sandbox = Tenant.objects.filter(parent_tenant=tenant, is_sandbox=True).first()
        if sandbox is None:
            raise
        return sandbox

    logger.info(
        "sandbox.provisioned",
        extra={"data": {"tenant_id": str(tenant.id), "sandbox_tenant_id": str(sandbox.id)}},
    )
    return sandbox
