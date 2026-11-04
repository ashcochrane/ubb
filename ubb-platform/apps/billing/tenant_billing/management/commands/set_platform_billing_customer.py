"""``set_platform_billing_customer`` — the operator path for the Stripe customer
UBB invoices a tenant's platform fee to (R10 Stage C3, F-10, RULED Q6).

UBB bills its own platform fee to the tenant as a customer of UBB's Stripe
account (``StripeService.create_tenant_platform_invoice``), and nothing wrote
that customer until C3, so every fee period stayed ``closed`` for ever. This
command is the ONE supported way to write it: there is no tenant self-service
route, no Django admin form and no public webhook event for it.

    manage.py set_platform_billing_customer --tenant <tenant id> \\
        --stripe-customer-id cus_... [--verify] [--operator <operator id>]

It validates the id's shape; with ``--verify`` it asks Stripe for the customer
through the guarded wrapper (``stripe_call``) under UBB's platform key, and is
refused by name, before any request, where that key is not configured; then it
writes the id and records the governance action
``tenant.platform_billing_customer_set`` under the operator actor, in one
transaction. A refusal at any step writes nothing. ``--tenant`` takes the
tenant's id: UBB's Tenant has no slug.
"""
import stripe
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.billing.stripe.services.stripe_service import field, stripe_call
from apps.billing.tenant_billing.models import BillingTenantConfig, is_a_stripe_customer_id
from apps.platform.audit.actors import operator_actor
from apps.platform.audit.ledger import record as audit_record
from apps.platform.tenants.models import Tenant
from core.exceptions import (
    StripeFatalError,
    StripeNotConfigured,
    StripePaymentError,
    StripeTransientError,
)
from core.vocabulary import (
    AUDIT_ACTION_TENANT_PLATFORM_BILLING_CUSTOMER_SET,
    AUDIT_RESOURCE_TYPE_TENANT,
)


class Command(BaseCommand):
    help = (
        "Set the Stripe customer UBB invoices a tenant's platform fee to (on UBB's "
        "own Stripe account), optionally verifying it with Stripe first, and record "
        "the change in the tenant's governance audit ledger under the operator."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="The tenant's id.")
        parser.add_argument(
            "--stripe-customer-id", required=True, dest="stripe_customer_id",
            help="The tenant's customer on UBB's Stripe account (cus_...).")
        parser.add_argument(
            "--verify", action="store_true",
            help="Retrieve the customer from Stripe under UBB's platform key "
                 "(STRIPE_SECRET_KEY) before writing; refused if the key is not set.")
        parser.add_argument(
            "--operator", default="",
            help="The acting UBB operator's id, kept on the audit entry.")

    def handle(self, *args, **options):
        tenant = self._tenant(options["tenant"])
        stripe_customer_id = options["stripe_customer_id"]
        if not is_a_stripe_customer_id(stripe_customer_id):
            raise CommandError(
                f"{stripe_customer_id!r} is not a Stripe customer id (expected "
                "'cus_' followed by letters and digits). Nothing was written.")

        verified = False
        if options["verify"]:
            self._verify(stripe_customer_id)
            verified = True

        with transaction.atomic():
            config, _ = BillingTenantConfig.objects.select_for_update().get_or_create(
                tenant=tenant)
            previous = config.stripe_customer_id
            config.stripe_customer_id = stripe_customer_id
            config.save(update_fields=["stripe_customer_id", "updated_at"])
            audit_record(
                action=AUDIT_ACTION_TENANT_PLATFORM_BILLING_CUSTOMER_SET,
                tenant_id=tenant.id,
                resource_type=AUDIT_RESOURCE_TYPE_TENANT,
                resource_id=tenant.id,
                metadata={"stripe_customer_id": stripe_customer_id,
                          "previous_stripe_customer_id": previous,
                          "verified": verified},
                actor=operator_actor(options["operator"]),
            )

        self.stdout.write(self.style.SUCCESS(
            f"Tenant {tenant.id}: platform billing customer set to {stripe_customer_id}"
            + (" (verified with Stripe)" if verified else " (not verified with Stripe)")
            + ". Closed fee periods waiting for it are invoiced by the next "
              "generate_tenant_platform_invoices run."))

    @staticmethod
    def _tenant(tenant_id):
        try:
            return Tenant.objects.get(id=tenant_id)
        except (Tenant.DoesNotExist, ValidationError, ValueError):
            raise CommandError(f"No tenant found with id={tenant_id!r}. Nothing was written.")

    @staticmethod
    def _verify(stripe_customer_id):
        """Retrieve the customer from UBB's own Stripe account (no connected
        account: the platform fee is UBB billing the tenant). ``stripe_call``
        refuses an empty key before any request, naming ``STRIPE_SECRET_KEY``."""
        try:
            customer = stripe_call(
                stripe.Customer.retrieve, api_key=settings.STRIPE_SECRET_KEY,
                id=stripe_customer_id)
        except StripeNotConfigured as exc:
            raise CommandError(f"--verify refused: {exc} Nothing was written.")
        except (StripeFatalError, StripeTransientError, StripePaymentError) as exc:
            raise CommandError(
                f"--verify failed: Stripe did not confirm customer {stripe_customer_id}: "
                f"{exc} Nothing was written.")
        if field(customer, "deleted", False) is True:
            raise CommandError(
                f"--verify failed: Stripe customer {stripe_customer_id} is deleted. "
                "Nothing was written.")
