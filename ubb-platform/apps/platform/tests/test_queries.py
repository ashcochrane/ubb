from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.queries import (
    get_tenant_stripe_account,
    get_customer_stripe_id,
    get_stripe_customer_holders,
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


class GetStripeCustomerHoldersTest(TestCase):
    """The holders of one Stripe customer id in one namespace (connected
    account + mode), every one of them (R10 Stage C4, PLAN §7 item 33)."""

    def _holder(self, customer):
        return {"customer_id": str(customer.id), "tenant_id": str(customer.tenant_id)}

    def test_answers_every_duplicate_holder_and_never_picks_one(self):
        tenant = Tenant.objects.create(name="Test", stripe_connected_account_id="acct_dup")
        a = Customer.objects.create(tenant=tenant, external_id="a", stripe_customer_id="cus_dup")
        b = Customer.objects.create(tenant=tenant, external_id="b", stripe_customer_id="cus_dup")
        Customer.objects.create(tenant=tenant, external_id="c", stripe_customer_id="cus_other")
        Customer.objects.create(tenant=tenant, external_id="d")  # no stripe id

        result = get_stripe_customer_holders(
            "acct_dup", livemode=True, stripe_customer_id="cus_dup")
        self.assertEqual(result, sorted([self._holder(a), self._holder(b)],
                                        key=lambda h: h["customer_id"]))

    def test_the_namespace_spans_every_tenant_on_the_account_in_that_mode(self):
        x = Tenant.objects.create(name="X", stripe_connected_account_id="acct_shared")
        y = Tenant.objects.create(name="Y", stripe_connected_account_id="acct_shared")
        elsewhere = Tenant.objects.create(name="Z", stripe_connected_account_id="acct_other")
        cx = Customer.objects.create(tenant=x, external_id="x", stripe_customer_id="cus_s")
        cy = Customer.objects.create(tenant=y, external_id="y", stripe_customer_id="cus_s")
        Customer.objects.create(tenant=elsewhere, external_id="z", stripe_customer_id="cus_s")

        result = get_stripe_customer_holders(
            "acct_shared", livemode=True, stripe_customer_id="cus_s")
        self.assertEqual({h["customer_id"] for h in result}, {str(cx.id), str(cy.id)})

    def test_livemode_separates_a_live_tenant_from_its_sandbox(self):
        from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox

        live = Tenant.objects.create(name="Live", stripe_connected_account_id="acct_pair")
        sandbox = get_or_create_sandbox(live)
        Tenant.objects.filter(id=sandbox.id).update(stripe_connected_account_id="acct_pair")
        lc = Customer.objects.create(tenant=live, external_id="a", stripe_customer_id="cus_same")
        sc = Customer.objects.create(tenant=sandbox, external_id="a", stripe_customer_id="cus_same")

        self.assertEqual(get_stripe_customer_holders(
            "acct_pair", livemode=True, stripe_customer_id="cus_same"), [self._holder(lc)])
        self.assertEqual(get_stripe_customer_holders(
            "acct_pair", livemode=False, stripe_customer_id="cus_same"), [self._holder(sc)])

    def test_a_soft_deleted_customer_holds_nothing(self):
        tenant = Tenant.objects.create(name="Test", stripe_connected_account_id="acct_del")
        gone = Customer.objects.create(tenant=tenant, external_id="gone", stripe_customer_id="cus_g")
        gone.soft_delete()
        self.assertEqual(get_stripe_customer_holders(
            "acct_del", livemode=True, stripe_customer_id="cus_g"), [])

    def test_a_blank_id_or_account_has_no_holder(self):
        tenant = Tenant.objects.create(name="Test", stripe_connected_account_id="acct_b")
        Customer.objects.create(tenant=tenant, external_id="c1")
        self.assertEqual(get_stripe_customer_holders(
            "acct_b", livemode=True, stripe_customer_id=""), [])
        self.assertEqual(get_stripe_customer_holders(
            "", livemode=True, stripe_customer_id="cus_x"), [])
