import json
from datetime import date
from django.test import TestCase, Client
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.invoicing.models import CustomerUsageInvoice
from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
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


def _make_usage_invoice(tenant, customer):
    return CustomerUsageInvoice.objects.create(
        tenant=tenant,
        customer=customer,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        total_billed_micros=12_340_000,
        status="pushed",
        payment_status="open",
        stripe_invoice_id="in_usage_test",
        hosted_invoice_url="https://stripe.test/usage",
        invoice_pdf="https://stripe.test/usage.pdf",
    )


def _make_subscription_invoice(tenant, customer):
    sub = StripeSubscription.objects.create(
        tenant=tenant,
        customer=customer,
        stripe_subscription_id="sub_test",
        stripe_product_name="Pro",
        status="active",
        amount_micros=20_000_000,
        interval="month",
        quantity=1,
        current_period_start=timezone.now(),
        current_period_end=timezone.now(),
        last_synced_at=timezone.now(),
    )
    return SubscriptionInvoice.objects.create(
        tenant=tenant,
        customer=customer,
        stripe_subscription=sub,
        stripe_invoice_id="in_sub_test",
        amount_paid_micros=20_000_000,
        status="paid",
        hosted_invoice_url="https://stripe.test/sub",
        invoice_pdf="https://stripe.test/sub.pdf",
    )


class WidgetUsageAndSubscriptionInvoiceTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            products=["metering", "billing"],
        )

    def _token(self, customer):
        return create_widget_token(
            self.tenant.widget_secret, str(customer.id), str(self.tenant.id)
        )

    def _get(self, path, customer):
        return self.http_client.get(
            path, HTTP_AUTHORIZATION=f"Bearer {self._token(customer)}"
        )

    def test_business_sees_its_usage_invoice(self):
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business",
            billing_topology="pooled",
        )
        _make_usage_invoice(self.tenant, business)
        resp = self._get("/api/v1/me/usage-invoices", business)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertEqual(row["total_billed_micros"], 12_340_000)
        self.assertEqual(row["payment_status"], "open")
        self.assertEqual(row["hosted_invoice_url"], "https://stripe.test/usage")
        self.assertEqual(row["invoice_pdf"], "https://stripe.test/usage.pdf")
        self.assertEqual(row["stripe_invoice_id"], "in_usage_test")
        self.assertEqual(row["period_start"], "2026-05-01")
        self.assertEqual(row["period_end"], "2026-05-31")

    def test_business_sees_its_subscription_invoice(self):
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz2", account_type="business",
            billing_topology="pooled",
        )
        _make_subscription_invoice(self.tenant, business)
        resp = self._get("/api/v1/me/subscription-invoices", business)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertEqual(row["amount_paid_micros"], 20_000_000)
        self.assertEqual(row["status"], "paid")
        self.assertEqual(row["hosted_invoice_url"], "https://stripe.test/sub")
        self.assertEqual(row["invoice_pdf"], "https://stripe.test/sub.pdf")

    def test_pooled_seat_sees_no_sibling_business_invoices(self):
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz3", account_type="business",
            billing_topology="pooled",
        )
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat3", account_type="seat",
            parent=business,
        )
        # Both invoices belong to the BUSINESS (consolidated bill).
        _make_usage_invoice(self.tenant, business)
        _make_subscription_invoice(self.tenant, business)

        usage_resp = self._get("/api/v1/me/usage-invoices", seat)
        self.assertEqual(usage_resp.status_code, 200)
        self.assertEqual(usage_resp.json()["data"], [])

        sub_resp = self._get("/api/v1/me/subscription-invoices", seat)
        self.assertEqual(sub_resp.status_code, 200)
        self.assertEqual(sub_resp.json()["data"], [])

    def test_individual_sees_its_own_usage_invoice(self):
        individual = Customer.objects.create(
            tenant=self.tenant, external_id="indiv", account_type="individual",
        )
        _make_usage_invoice(self.tenant, individual)
        resp = self._get("/api/v1/me/usage-invoices", individual)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["data"]), 1)


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
