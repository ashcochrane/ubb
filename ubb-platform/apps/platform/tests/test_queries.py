from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.queries import (
    get_tenant_stripe_account,
    get_customer_stripe_id,
    get_customers_by_stripe_id,
)


class GetTenantStripeAccountTest(TestCase):
    def test_returns_account_id(self):
        tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_123"
        )
        result = get_tenant_stripe_account(tenant.id)
        self.assertEqual(result, "acct_123")

    def test_returns_none_when_empty(self):
        tenant = Tenant.objects.create(name="Test")
        result = get_tenant_stripe_account(tenant.id)
        self.assertIsNone(result)


class GetCustomerStripeIdTest(TestCase):
    def test_returns_stripe_id(self):
        tenant = Tenant.objects.create(name="Test")
        customer = Customer.objects.create(
            tenant=tenant, external_id="c1", stripe_customer_id="cus_abc"
        )
        result = get_customer_stripe_id(customer.id)
        self.assertEqual(result, "cus_abc")

    def test_returns_none_when_empty(self):
        tenant = Tenant.objects.create(name="Test")
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        result = get_customer_stripe_id(customer.id)
        self.assertIsNone(result)


class GetCustomersByStripeIdTest(TestCase):
    def test_returns_mapping(self):
        tenant = Tenant.objects.create(name="Test")
        c1 = Customer.objects.create(
            tenant=tenant, external_id="c1", stripe_customer_id="cus_aaa"
        )
        c2 = Customer.objects.create(
            tenant=tenant, external_id="c2", stripe_customer_id="cus_bbb"
        )
        Customer.objects.create(tenant=tenant, external_id="c3")  # no stripe id

        result = get_customers_by_stripe_id(tenant.id)
        self.assertEqual(result, {
            "cus_aaa": str(c1.id),
            "cus_bbb": str(c2.id),
        })

    def test_returns_empty_dict_when_no_stripe_customers(self):
        tenant = Tenant.objects.create(name="Test")
        Customer.objects.create(tenant=tenant, external_id="c1")
        result = get_customers_by_stripe_id(tenant.id)
        self.assertEqual(result, {})
