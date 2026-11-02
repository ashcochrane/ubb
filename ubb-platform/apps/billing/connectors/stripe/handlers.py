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
from apps.platform.events.schemas import WalletBalanceLow
from apps.platform.queries import get_tenant_stripe_account
from core.exceptions import NoWalletSubjectError

logger = logging.getLogger(__name__)


def handle_balance_low_stripe(event_id, payload):
    """When balance is low and tenant has Stripe, create auto top-up attempt
    and dispatch charge task."""
    evt = WalletBalanceLow.from_payload(payload)
    tenant_id = evt.tenant_id
    customer_id = evt.customer_id

    if not get_tenant_stripe_account(tenant_id):
        return  # No Stripe connector -- tenant handles via webhook

    from apps.platform.tenants.models import Tenant
    if not Tenant.objects.filter(id=tenant_id, charges_enabled=True).exists():
        return  # Connected account is not charge-ready -- never charge it

    from apps.billing.connectors.stripe.tasks import charge_auto_top_up_task

    try:
        with transaction.atomic():
            wallet, customer = lock_for_billing(customer_id)
            attempt = AutoTopUpService.create_pending_attempt(customer, wallet)
            if attempt:
                transaction.on_commit(lambda aid=attempt.id: charge_auto_top_up_task.delay(str(aid)))
    except NoWalletSubjectError as refused:
        # The wallet boundary refused: the tenant's billing mode holds no
        # wallet. A low balance is only ever announced by a prepaid drawdown,
        # so this is reached only if the tenant left `prepaid` between the
        # announcement and its handling. Nothing a retry could change — an
        # outbox handler that raises is retried for hours and then
        # dead-lettered — so the refusal is recorded here by name and the
        # event is consumed: no attempt, no charge.
        logger.warning("auto_top_up.refused_no_wallet_subject", extra={"data": {
            "event_id": event_id, "tenant_id": str(tenant_id),
            "customer_id": str(customer_id),
            "billing_mode": refused.billing_mode}})
