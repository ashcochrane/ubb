import logging

from django.db import transaction

from apps.platform.tenants.models import Tenant
from apps.billing.tenant_billing.services import TenantBillingService

logger = logging.getLogger("ubb.events")


def handle_usage_recorded(data):
    tenant = Tenant.objects.get(id=data["tenant_id"])
    billed_cost_micros = data.get("cost_micros", 0)
    if billed_cost_micros > 0:
        TenantBillingService.accumulate_usage(tenant, billed_cost_micros)

    # Dispatch auto-topup charge task if metering created a pending attempt
    attempt_id = data.get("auto_topup_attempt_id")
    if attempt_id:
        from apps.billing.stripe.tasks import charge_auto_topup_task
        transaction.on_commit(
            lambda aid=attempt_id: charge_auto_topup_task.delay(aid)
        )
