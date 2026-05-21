from decimal import Decimal

from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.queries import (
    get_billing_config,
    get_customer_min_balance,
    get_customer_balance,
)


class GetBillingConfigTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")

    def test_creates_config_on_first_access(self):
        config = get_billing_config(self.tenant.id)
        self.assertEqual(config.tenant_id, self.tenant.id)
        self.assertEqual(config.stripe_customer_id, "")
        self.assertEqual(config.platform_fee_percentage, Decimal("1.00"))
        self.assertEqual(config.min_balance_micros, 0)
        self.assertIsNone(config.run_cost_limit_micros)
        self.assertIsNone(config.hard_stop_balance_micros)

    def test_returns_existing_config(self):
        from apps.billing.tenant_billing.models import BillingTenantConfig
        BillingTenantConfig.objects.create(
            tenant=self.tenant,
            stripe_customer_id="cus_abc",
            platform_fee_percentage=Decimal("2.50"),
            min_balance_micros=5_000_000,
        )
        config = get_billing_config(self.tenant.id)
        self.assertEqual(config.stripe_customer_id, "cus_abc")
        self.assertEqual(config.platform_fee_percentage, Decimal("2.50"))
        self.assertEqual(config.min_balance_micros, 5_000_000)

    def test_idempotent_lazy_creation(self):
        get_billing_config(self.tenant.id)
        get_billing_config(self.tenant.id)
        from apps.billing.tenant_billing.models import BillingTenantConfig
        self.assertEqual(
            BillingTenantConfig.objects.filter(tenant=self.tenant).count(), 1
        )


class GetCustomerMinBalanceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def test_returns_zero_when_no_profile_and_no_config(self):
        result = get_customer_min_balance(self.customer.id, self.tenant.id)
        self.assertEqual(result, 0)

    def test_returns_tenant_default_when_no_customer_override(self):
        from apps.billing.tenant_billing.models import BillingTenantConfig
        BillingTenantConfig.objects.create(
            tenant=self.tenant, min_balance_micros=5_000_000,
        )
        result = get_customer_min_balance(self.customer.id, self.tenant.id)
        self.assertEqual(result, 5_000_000)

    def test_customer_override_takes_precedence(self):
        from apps.billing.tenant_billing.models import BillingTenantConfig
        from apps.billing.wallets.models import CustomerBillingProfile
        BillingTenantConfig.objects.create(
            tenant=self.tenant, min_balance_micros=5_000_000,
        )
        CustomerBillingProfile.objects.create(
            customer=self.customer, min_balance_micros=10_000_000,
        )
        result = get_customer_min_balance(self.customer.id, self.tenant.id)
        self.assertEqual(result, 10_000_000)

    def test_customer_override_zero_is_valid(self):
        from apps.billing.tenant_billing.models import BillingTenantConfig
        from apps.billing.wallets.models import CustomerBillingProfile
        BillingTenantConfig.objects.create(
            tenant=self.tenant, min_balance_micros=5_000_000,
        )
        CustomerBillingProfile.objects.create(
            customer=self.customer, min_balance_micros=0,
        )
        result = get_customer_min_balance(self.customer.id, self.tenant.id)
        self.assertEqual(result, 0)


class GetCustomerBalanceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def test_returns_zero_when_no_wallet(self):
        result = get_customer_balance(self.customer.id)
        self.assertEqual(result, 0)

    def test_returns_wallet_balance(self):
        from apps.billing.wallets.models import Wallet
        Wallet.objects.create(customer=self.customer, balance_micros=7_000_000)
        result = get_customer_balance(self.customer.id)
        self.assertEqual(result, 7_000_000)
