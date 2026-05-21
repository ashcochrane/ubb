"""Stripe connector outbox event handlers.

These handlers subscribe to billing events and handle Stripe
payment operations. They are registered in the connector's
AppConfig.ready() and only run when the tenant has a
stripe_connected_account_id configured.
"""
import logging

from django.db import transaction

from apps.billing.locking import lock_for_billing
from apps.billing.topups.services import AutoTopUpService
from apps.platform.queries import get_tenant_stripe_account

logger = logging.getLogger(__name__)


def handle_balance_low_stripe(event_id, payload):
    """When balance is low and tenant has Stripe, create auto-topup attempt
    and dispatch charge task."""
    tenant_id = payload["tenant_id"]
    customer_id = payload["customer_id"]

    if not get_tenant_stripe_account(tenant_id):
        return  # No Stripe connector -- tenant handles via webhook

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer_id)
        attempt = AutoTopUpService.create_pending_attempt(customer, wallet)

    if attempt:
        from apps.billing.connectors.stripe.tasks import charge_auto_topup_task
        charge_auto_topup_task.delay(str(attempt.id))
