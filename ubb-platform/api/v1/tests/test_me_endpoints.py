import json
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from core.widget_auth import create_widget_token


class WidgetBalanceTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            products=["metering", "billing"],
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )
        self.wallet = Wallet.objects.create(customer=self.customer)
        self.wallet.balance_micros = 50_000_000
        self.wallet.save()
        self.token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id)
        )

    def test_get_balance(self):
        response = self.http_client.get(
            "/api/v1/me/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["balance_micros"], 50_000_000)
        self.assertEqual(body["currency"], "USD")

    def test_no_token_returns_401(self):
        response = self.http_client.get("/api/v1/me/balance")
        self.assertEqual(response.status_code, 401)

    def test_expired_token_returns_401(self):
        token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id),
            expires_in=-1,
        )
        response = self.http_client.get(
            "/api/v1/me/balance",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 401)


class WidgetTransactionsTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            products=["metering", "billing"],
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )
        wallet = Wallet.objects.create(customer=self.customer)
        wallet.balance_micros = 100_000_000
        wallet.save()
        for i in range(3):
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type="TOP_UP",
                amount_micros=10_000_000,
                balance_after_micros=100_000_000 + (i + 1) * 10_000_000,
                description=f"Top up {i}",
            )
        self.token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id)
        )

    def test_list_transactions(self):
        response = self.http_client.get(
            "/api/v1/me/transactions",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["data"]), 3)


class WidgetTopUpTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            products=["metering", "billing"],
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1",
            stripe_customer_id="cus_test",
        )
        self.token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id)
        )

    def test_create_topup_requires_amount(self):
        response = self.http_client.post(
            "/api/v1/me/top-up",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, 422)


class WidgetProductGatingTest(TestCase):
    """Tenants without billing product get 403 on widget endpoints."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Metering Only", stripe_connected_account_id="acct_test",
            products=["metering"],
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c_gate"
        )
        self.token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id)
        )

    def test_tenant_without_billing_gets_403_on_widget_balance(self):
        response = self.http_client.get(
            "/api/v1/me/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, 403)

    def test_tenant_without_billing_gets_403_on_widget_transactions(self):
        response = self.http_client.get(
            "/api/v1/me/transactions",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, 403)

    def test_tenant_without_billing_gets_403_on_widget_invoices(self):
        response = self.http_client.get(
            "/api/v1/me/invoices",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, 403)
