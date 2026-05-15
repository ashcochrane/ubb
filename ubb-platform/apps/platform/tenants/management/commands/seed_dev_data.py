from decimal import Decimal
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from apps.platform.tenants.models import Tenant, TenantApiKey, TenantUser
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
            "--clerk-user-id",
            default="",
            help="Clerk user ID to link to the seeded tenant (creates TenantUser).",
        )
        parser.add_argument(
            "--clerk-email",
            default="dev@example.com",
            help="Email for the TenantUser (default: dev@example.com).",
        )

    def handle(self, *args, **options):
        # Create or get tenant
        try:
            tenant = Tenant.objects.get(name=options["tenant_name"])
            created = False
        except Tenant.DoesNotExist:
            # Check if database has missing_rate_policy column (stale schema)
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT EXISTS(
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='ubb_tenant' AND column_name='missing_rate_policy'
                    )
                """)
                has_missing_rate_policy = cursor.fetchone()[0]

            if has_missing_rate_policy:
                # Insert using raw SQL with missing_rate_policy default
                import secrets
                tenant = Tenant(
                    name=options["tenant_name"],
                    stripe_connected_account_id=options["stripe_account"],
                    platform_fee_percentage=Decimal(options["platform_fee"]),
                    products=["metering"],
                    onboarding_completed_at=timezone.now(),
                )
                tenant.widget_secret = secrets.token_urlsafe(48)
                with connection.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO ubb_tenant (
                            id, created_at, updated_at, name, stripe_connected_account_id,
                            min_balance_micros, platform_fee_percentage, is_active,
                            branding_config, metadata, widget_secret, stripe_customer_id,
                            products, group_label, default_margin_pct, missing_rate_policy,
                            onboarding_completed_at
                        ) VALUES (
                            %s, now(), now(), %s, %s, 0, %s, true, %s, %s, %s, %s,
                            %s, %s, 0, %s, %s
                        )
                    """, [
                        str(tenant.id),
                        tenant.name,
                        tenant.stripe_connected_account_id,
                        str(tenant.platform_fee_percentage),
                        json.dumps(tenant.branding_config),
                        json.dumps(tenant.metadata),
                        tenant.widget_secret,
                        tenant.stripe_customer_id,
                        json.dumps(tenant.products),
                        tenant.group_label,
                        'allow',
                        timezone.now().isoformat(),
                    ])
                created = True
            else:
                # Normal ORM creation
                tenant, created = Tenant.objects.get_or_create(
                    name=options["tenant_name"],
                    defaults={
                        "stripe_connected_account_id": options["stripe_account"],
                        "platform_fee_percentage": Decimal(options["platform_fee"]),
                    },
                )
        if created:
            self.stdout.write(f"Created tenant: {tenant.name}")
        else:
            # Update stripe account if changed
            if tenant.stripe_connected_account_id != options["stripe_account"]:
                tenant.stripe_connected_account_id = options["stripe_account"]
                tenant.save(update_fields=["stripe_connected_account_id", "updated_at"])
            self.stdout.write(f"Updated existing tenant: {tenant.name}")

            # Ensure existing tenant has metering product and is marked as onboarded
            if "metering" not in tenant.products:
                tenant.products = sorted({*tenant.products, "metering"})
            if tenant.onboarding_completed_at is None:
                tenant.onboarding_completed_at = timezone.now()
            tenant.save(update_fields=["products", "onboarding_completed_at", "updated_at"])

        # Create TenantUser if clerk_user_id provided
        if options["clerk_user_id"]:
            tu, tu_created = TenantUser.objects.get_or_create(
                clerk_user_id=options["clerk_user_id"],
                defaults={
                    "tenant": tenant,
                    "email": options["clerk_email"],
                    "role": "owner",
                },
            )
            self.stdout.write(
                f"{'Created' if tu_created else 'Existing'} TenantUser: {tu.email}"
            )

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
