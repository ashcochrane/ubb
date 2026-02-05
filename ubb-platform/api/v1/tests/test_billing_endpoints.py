import json

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer


class BillingProductGatingTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant_no_billing = Tenant.objects.create(
            name="No Billing", products=["metering"]
        )
        self.key_obj_no, self.raw_key_no = TenantApiKey.create_key(
            self.tenant_no_billing, label="test"
        )
        self.tenant_with_billing = Tenant.objects.create(
            name="Has Billing", products=["billing"]
        )
        self.key_obj_yes, self.raw_key_yes = TenantApiKey.create_key(
            self.tenant_with_billing, label="test"
        )
        self.customer_no = Customer.objects.create(
            tenant=self.tenant_no_billing, external_id="cust_no_bill"
        )
        self.customer_yes = Customer.objects.create(
            tenant=self.tenant_with_billing, external_id="cust_bill1"
        )

    def test_tenant_without_billing_gets_403_on_balance(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer_no.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_no}",
        )
        self.assertEqual(response.status_code, 403)

    def test_tenant_with_billing_can_check_balance(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer_yes.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_yes}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("balance_micros", body)
        self.assertIn("currency", body)

    def test_tenant_without_billing_gets_403_on_pre_check(self):
        response = self.http_client.post(
            "/api/v1/billing/pre-check",
            data=json.dumps({"customer_id": str(self.customer_no.id)}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_no}",
        )
        self.assertEqual(response.status_code, 403)

    def test_tenant_with_billing_can_pre_check(self):
        response = self.http_client.post(
            "/api/v1/billing/pre-check",
            data=json.dumps({"customer_id": str(self.customer_yes.id)}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_yes}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("allowed", body)

    def test_tenant_without_billing_gets_403_on_transactions(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer_no.id}/transactions",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_no}",
        )
        self.assertEqual(response.status_code, 403)

    def test_tenant_with_billing_can_list_transactions(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer_yes.id}/transactions",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_yes}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("data", body)
        self.assertIn("has_more", body)

    def test_tenant_without_billing_gets_403_on_billing_periods(self):
        response = self.http_client.get(
            "/api/v1/billing/tenant/billing-periods",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_no}",
        )
        self.assertEqual(response.status_code, 403)

    def test_tenant_with_billing_can_list_billing_periods(self):
        response = self.http_client.get(
            "/api/v1/billing/tenant/billing-periods",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_yes}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("data", body)
        self.assertIn("has_more", body)

    def test_tenant_without_billing_gets_403_on_invoices(self):
        response = self.http_client.get(
            "/api/v1/billing/tenant/invoices",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_no}",
        )
        self.assertEqual(response.status_code, 403)

    def test_tenant_with_billing_can_list_invoices(self):
        response = self.http_client.get(
            "/api/v1/billing/tenant/invoices",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_yes}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("data", body)
        self.assertIn("has_more", body)


class BillingDebitEndpointTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Debit Tenant", products=["billing"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(
            self.tenant, label="test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_debit_1"
        )
        # Give the wallet some balance
        self.customer.wallet.balance_micros = 10_000_000
        self.customer.wallet.save()

    def test_debit_success(self):
        response = self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({
                "customer_id": "cust_debit_1",
                "amount_micros": 1_500_000,
                "reference": "evt_123",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["new_balance_micros"], 8_500_000)
        self.assertIn("transaction_id", body)

    def test_debit_reduces_balance(self):
        self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({
                "customer_id": "cust_debit_1",
                "amount_micros": 3_000_000,
                "reference": "evt_456",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.customer.wallet.refresh_from_db()
        self.assertEqual(self.customer.wallet.balance_micros, 7_000_000)

    def test_debit_creates_wallet_transaction(self):
        response = self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({
                "customer_id": "cust_debit_1",
                "amount_micros": 2_000_000,
                "reference": "evt_789",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        body = response.json()
        from apps.platform.customers.models import WalletTransaction
        txn = WalletTransaction.objects.get(id=body["transaction_id"])
        self.assertEqual(txn.transaction_type, "USAGE_DEDUCTION")
        self.assertEqual(txn.amount_micros, -2_000_000)
        self.assertEqual(txn.reference_id, "evt_789")
        self.assertEqual(txn.description, "External debit")

    def test_debit_unknown_customer_returns_404(self):
        response = self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({
                "customer_id": "nonexistent",
                "amount_micros": 1_000_000,
                "reference": "ref_1",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 404)

    def test_debit_tenant_isolation(self):
        """Customer from another tenant should not be accessible."""
        other_tenant = Tenant.objects.create(
            name="Other Tenant", products=["billing"]
        )
        other_key_obj, other_raw_key = TenantApiKey.create_key(other_tenant, label="test")
        response = self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({
                "customer_id": "cust_debit_1",
                "amount_micros": 500_000,
                "reference": "ref_2",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {other_raw_key}",
        )
        self.assertEqual(response.status_code, 404)

    def test_debit_without_billing_product_returns_403(self):
        tenant_no_billing = Tenant.objects.create(
            name="No Billing", products=["metering"]
        )
        key_obj, raw_key = TenantApiKey.create_key(tenant_no_billing, label="test")
        response = self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({
                "customer_id": "cust_debit_1",
                "amount_micros": 500_000,
                "reference": "ref_3",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)


class BillingCreditEndpointTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Credit Tenant", products=["billing"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(
            self.tenant, label="test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_credit_1"
        )
        # Start with zero balance
        self.customer.wallet.balance_micros = 0
        self.customer.wallet.save()

    def test_credit_success(self):
        response = self.http_client.post(
            "/api/v1/billing/credit",
            data=json.dumps({
                "customer_id": "cust_credit_1",
                "amount_micros": 5_000_000,
                "source": "manual_adjustment",
                "reference": "adj_001",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["new_balance_micros"], 5_000_000)
        self.assertIn("transaction_id", body)

    def test_credit_increases_balance(self):
        self.http_client.post(
            "/api/v1/billing/credit",
            data=json.dumps({
                "customer_id": "cust_credit_1",
                "amount_micros": 7_000_000,
                "source": "promo",
                "reference": "promo_001",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.customer.wallet.refresh_from_db()
        self.assertEqual(self.customer.wallet.balance_micros, 7_000_000)

    def test_credit_creates_adjustment_transaction(self):
        response = self.http_client.post(
            "/api/v1/billing/credit",
            data=json.dumps({
                "customer_id": "cust_credit_1",
                "amount_micros": 3_000_000,
                "source": "goodwill",
                "reference": "gw_001",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        body = response.json()
        from apps.platform.customers.models import WalletTransaction
        txn = WalletTransaction.objects.get(id=body["transaction_id"])
        self.assertEqual(txn.transaction_type, "ADJUSTMENT")
        self.assertEqual(txn.amount_micros, 3_000_000)
        self.assertEqual(txn.reference_id, "gw_001")
        self.assertEqual(txn.description, "Credit: goodwill")

    def test_credit_unknown_customer_returns_404(self):
        response = self.http_client.post(
            "/api/v1/billing/credit",
            data=json.dumps({
                "customer_id": "nonexistent",
                "amount_micros": 1_000_000,
                "source": "test",
                "reference": "ref_1",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 404)

    def test_credit_tenant_isolation(self):
        """Customer from another tenant should not be accessible."""
        other_tenant = Tenant.objects.create(
            name="Other Tenant 2", products=["billing"]
        )
        other_key_obj, other_raw_key = TenantApiKey.create_key(other_tenant, label="test")
        response = self.http_client.post(
            "/api/v1/billing/credit",
            data=json.dumps({
                "customer_id": "cust_credit_1",
                "amount_micros": 500_000,
                "source": "test",
                "reference": "ref_2",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {other_raw_key}",
        )
        self.assertEqual(response.status_code, 404)

    def test_credit_without_billing_product_returns_403(self):
        tenant_no_billing = Tenant.objects.create(
            name="No Billing 2", products=["metering"]
        )
        key_obj, raw_key = TenantApiKey.create_key(tenant_no_billing, label="test")
        response = self.http_client.post(
            "/api/v1/billing/credit",
            data=json.dumps({
                "customer_id": "cust_credit_1",
                "amount_micros": 500_000,
                "source": "test",
                "reference": "ref_3",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)
