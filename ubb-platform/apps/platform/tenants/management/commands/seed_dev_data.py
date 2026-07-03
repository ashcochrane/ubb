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
        parser.add_argument(
            "--billing-mode",
            default="postpaid",
            choices=["meter_only", "prepaid", "postpaid"],
            help=(
                "Tenant billing mode (default: postpaid). "
                "Use 'postpaid' or 'prepaid' to enable J2 subscription billing. "
                "'meter_only' = J1 cost-attribution only."
            ),
        )
        parser.add_argument(
            "--with-sandbox",
            action="store_true",
            help="Also provision the tenant's sandbox sibling and mint a ubb_test_ key.",
        )

    def handle(self, *args, **options):
        billing_mode = options["billing_mode"]
        # Products required for J2 (billing + subscriptions) when not meter_only.
        if billing_mode in ("prepaid", "postpaid"):
            products = ["metering", "billing", "subscriptions"]
        else:
            products = ["metering"]

        # Create or get tenant
        tenant, created = Tenant.objects.get_or_create(
            name=options["tenant_name"],
            defaults={
                "stripe_connected_account_id": options["stripe_account"],
                "billing_mode": billing_mode,
                "products": products,
            },
        )
        if not created:
            tenant.stripe_connected_account_id = options["stripe_account"]
            tenant.billing_mode = billing_mode
            tenant.products = products
            tenant.save(update_fields=[
                "stripe_connected_account_id", "billing_mode", "products", "updated_at"
            ])
            self.stdout.write(f"Updated existing tenant: {tenant.name}")
        else:
            self.stdout.write(f"Created tenant: {tenant.name}")
        self.stdout.write(f"  billing_mode={tenant.billing_mode}  products={tenant.products}")

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

        # Optional sandbox sibling + test key (routed at mint time)
        if options["with_sandbox"]:
            test_key_obj, raw_test_key = TenantApiKey.create_key(
                tenant, label="dev-seed-sandbox", is_test=True,
            )
            self.stdout.write(f"Sandbox tenant ID: {test_key_obj.tenant_id}")
            self.stdout.write(f"Sandbox test key:  {raw_test_key}")

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
        self.stdout.write("\nTest commands (server: python manage.py runserver 8001):\n")
        self.stdout.write(f'# Health check')
        self.stdout.write(f'curl http://localhost:8001/api/v1/health\n')
        self.stdout.write(f'# Get wallet balance')
        self.stdout.write(f'curl -H "Authorization: Bearer {raw_key}" '
                          f'http://localhost:8001/api/v1/billing/customers/{customer.id}/balance\n')
        self.stdout.write(f'# Create a cost rate card (2 micros per input_token)')
        self.stdout.write(
            f'curl -X POST -H "Authorization: Bearer {raw_key}" '
            f'-H "Content-Type: application/json" '
            f'-d \'{{"card_type": "cost", "metric_name": "input_tokens", '
            f'"pricing_model": "per_unit", "rate_per_unit_micros": 2, "unit_quantity": 1}}\' '
            f'http://localhost:8001/api/v1/metering/pricing/rate-cards\n')
        self.stdout.write(f'# Record a usage event (engine computes COGS from rate card)')
        self.stdout.write(
            f'curl -X POST -H "Authorization: Bearer {raw_key}" '
            f'-H "Content-Type: application/json" '
            f'-d \'{{"customer_id": "{customer.id}", "request_id": "req-1", '
            f'"idempotency_key": "idem-1", "product_id": "search", '
            f'"usage_metrics": {{"input_tokens": 1000}}}}\' '
            f'http://localhost:8001/api/v1/metering/usage\n')
        self.stdout.write(f'# Per-customer cost analytics')
        self.stdout.write(
            f'curl -H "Authorization: Bearer {raw_key}" '
            f'"http://localhost:8001/api/v1/metering/analytics/usage?customer_id={customer.id}"\n')
        self.stdout.write(f'# Me balance (widget JWT)')
        self.stdout.write(
            f'curl -H "Authorization: Bearer {widget_token}" '
            f'http://localhost:8001/api/v1/me/balance\n')
        self.stdout.write(
            f'# SDK quickstart — see ubb-sdk/README.md for the full Journey-1 happy path\n')

        # ---- Journey 2 endpoints (only meaningful when billing_mode != meter_only) ----
        self.stdout.write("=" * 60)
        if billing_mode == "meter_only":
            self.stdout.write("Journey 2 (subscriptions + seats) is NOT enabled.")
            self.stdout.write(
                "Re-run with --billing-mode postpaid to enable J2 (adds billing+subscriptions).\n")
        else:
            self.stdout.write("Journey 2 — subscriptions + seats + usage")
            self.stdout.write("=" * 60)
            self.stdout.write(
                "IMPORTANT: stripe_connected_account_id is a placeholder value.\n"
                "  For real Stripe billing you must complete Connect OAuth:\n"
                "    1. Call POST /api/v1/connect/start  (or client.start_connect_onboarding)\n"
                "    2. Visit the returned authorize_url in a browser\n"
                "    3. Confirm with GET /api/v1/connect/status (charges_enabled must be true)\n"
            )
            self.stdout.write("J2 API endpoints (server: python manage.py runserver 8001):\n")
            self.stdout.write(
                f'# Create a billing plan ($10/month + $5/seat)\n'
                f'curl -X POST -H "Authorization: Bearer {raw_key}" \\\n'
                f'  -H "Content-Type: application/json" \\\n'
                f'  -d \'{{"key":"pro-monthly","name":"Pro","access_fee_micros":10000000,'
                f'"per_seat_micros":5000000,"interval":"month"}}\' \\\n'
                f'  http://localhost:8001/api/v1/platform/plans\n'
            )
            self.stdout.write(
                f'# Subscribe the test customer (5 seats)\n'
                f'curl -X POST -H "Authorization: Bearer {raw_key}" \\\n'
                f'  -H "Content-Type: application/json" \\\n'
                f'  -d \'{{"plan_key":"pro-monthly","seats":5}}\' \\\n'
                f'  http://localhost:8001/api/v1/platform/customers/{customer.id}/subscribe\n'
            )
            self.stdout.write(
                f'# Change seat count\n'
                f'curl -X POST -H "Authorization: Bearer {raw_key}" \\\n'
                f'  -H "Content-Type: application/json" \\\n'
                f'  -d \'{{"seats":8}}\' \\\n'
                f'  http://localhost:8001/api/v1/platform/customers/{customer.id}/seats\n'
            )
            self.stdout.write(
                f'# End-customer views their invoices (widget JWT)\n'
                f'curl -H "Authorization: Bearer {widget_token}" \\\n'
                f'  http://localhost:8001/api/v1/me/usage-invoices\n'
                f'curl -H "Authorization: Bearer {widget_token}" \\\n'
                f'  http://localhost:8001/api/v1/me/subscription-invoices\n'
            )
            self.stdout.write(
                f'# SDK Journey 2 quickstart — see ubb-sdk/README.md ## Journey 2 section\n'
            )
