from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer


class Command(BaseCommand):
    help = "Seed development data: tenant, API key, and test customer with wallet."

    def add_arguments(self, parser):
        parser.add_argument(
            "--stripe-account",
            required=True,
            help="Stripe Connected Account ID for the tenant (acct_...)",
        )
        parser.add_argument(
            "--tenant-name",
            default="LocalScouta",
            help="Tenant name (default: LocalScouta)",
        )
        parser.add_argument(
            "--stripe-customer-id",
            default="",
            help="Stripe customer ID for the test customer (cus_...)",
        )
        parser.add_argument(
            "--platform-fee",
            default="2.50",
            help="Platform fee percentage (default: 2.50)",
        )

    def handle(self, *args, **options):
        # Create or get tenant
        tenant, created = Tenant.objects.get_or_create(
            name=options["tenant_name"],
            defaults={
                "stripe_connected_account_id": options["stripe_account"],
            },
        )
        if not created:
            tenant.stripe_connected_account_id = options["stripe_account"]
            tenant.save(update_fields=["stripe_connected_account_id", "updated_at"])
            self.stdout.write(f"Updated existing tenant: {tenant.name}")
        else:
            self.stdout.write(f"Created tenant: {tenant.name}")

        # Create or update billing config for this tenant
        from apps.billing.tenant_billing.models import BillingTenantConfig
        billing_config, bc_created = BillingTenantConfig.objects.get_or_create(
            tenant=tenant,
            defaults={
                "platform_fee_percentage": Decimal(options["platform_fee"]),
            },
        )
        if not bc_created:
            billing_config.platform_fee_percentage = Decimal(options["platform_fee"])
            billing_config.save(update_fields=["platform_fee_percentage", "updated_at"])
        self.stdout.write(f"{'Created' if bc_created else 'Updated'} billing config")

        # Create API key
        key_obj, raw_key = TenantApiKey.create_key(tenant, label="dev-seed")
        self.stdout.write(f"Created API key: {raw_key}")

        # Create test customer with wallet
        defaults = {}
        if options["stripe_customer_id"]:
            defaults["stripe_customer_id"] = options["stripe_customer_id"]
        customer, cust_created = Customer.objects.get_or_create(
            tenant=tenant,
            external_id="test-user-1",
            defaults=defaults,
        )
        if cust_created:
            self.stdout.write(f"Created customer: {customer.id}")
        else:
            self.stdout.write(f"Existing customer: {customer.id}")

        # Generate widget JWT
        from core.widget_auth import create_widget_token
        widget_token = create_widget_token(tenant.widget_secret, str(customer.id), str(tenant.id))

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("DEV SEED COMPLETE")
        self.stdout.write("=" * 60)
        self.stdout.write(f"Tenant ID:      {tenant.id}")
        self.stdout.write(f"Tenant name:    {tenant.name}")
        self.stdout.write(f"Widget secret:  {tenant.widget_secret}")
        self.stdout.write(f"API key:        {raw_key}")
        self.stdout.write(f"Customer ID:    {customer.id}")
        self.stdout.write(f"Stripe CID:     {customer.stripe_customer_id or '(not set)'}")
        self.stdout.write(f"Widget JWT:     {widget_token}")
        self.stdout.write("=" * 60)
        self.stdout.write("\nTest commands:\n")
        self.stdout.write(f'# Health check')
        self.stdout.write(f'curl http://localhost:8000/api/v1/health\n')
        self.stdout.write(f'# Get balance')
        self.stdout.write(f'curl -H "Authorization: Bearer {raw_key}" '
                          f'http://localhost:8000/api/v1/customers/{customer.id}/balance\n')
        self.stdout.write(f'# Record usage')
        self.stdout.write(
            f'curl -X POST -H "Authorization: Bearer {raw_key}" '
            f'-H "Content-Type: application/json" '
            f'-d \'{{"customer_id": "{customer.id}", "request_id": "req-1", '
            f'"idempotency_key": "idem-1", "cost_micros": 500000}}\' '
            f'http://localhost:8000/api/v1/usage\n')
        self.stdout.write(f'# Me balance (widget)')
        self.stdout.write(
            f'curl -H "Authorization: Bearer {widget_token}" '
            f'http://localhost:8000/api/v1/me/balance\n')
