import logging

from apps.platform.tenants.models import Tenant
from apps.billing.tenant_billing.services import TenantBillingService

logger = logging.getLogger("ubb.events")


def handle_usage_recorded(data):
    tenant = Tenant.objects.get(id=data["tenant_id"])
    billed_cost_micros = data.get("cost_micros", 0)
    if billed_cost_micros > 0:
        TenantBillingService.accumulate_usage(tenant, billed_cost_micros)
