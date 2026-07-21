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
        self.assertEqual(body["currency"], "usd")  # CUR-1: lowercase everywhere

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
        self.assertEqual(response["Content-Type"], "application/problem+json")
        self.assertEqual(response.json()["code"], "validation_error")


class WidgetTopUpReplayTest(TestCase):
    """#78: widget top-up carries a required idempotency_key; a replay never
    mints a second attempt or re-emits the event (connector-less branch)."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="No Stripe", stripe_connected_account_id="",
            products=["metering", "billing"],
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c_replay",
        )
        self.token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id)
        )

    def _topup(self, key):
        return self.http_client.post(
            "/api/v1/me/top-up",
            data=json.dumps({
                "amount_micros": 10_000_000,
                "success_url": "https://x.test/s",
                "cancel_url": "https://x.test/c",
                "idempotency_key": key,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

    def test_replay_answers_202_without_second_event_or_attempt(self):
        from apps.billing.topups.models import TopUpAttempt
        from apps.platform.events.models import OutboxEvent

        first = self._topup("w_dup")
        replay = self._topup("w_dup")

        self.assertEqual(first.status_code, 202)
        self.assertEqual(replay.status_code, 202)
        self.assertEqual(
            TopUpAttempt.objects.filter(customer=self.customer).count(), 1)
        self.assertEqual(
            OutboxEvent.objects.filter(
                event_type="billing.topup_requested").count(), 1)


class WidgetGrantsEnvelopeTest(TestCase):
    """#78: the /me grants list adopts the one cursor envelope."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Grants", products=["metering", "billing"],
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c_gr",
        )
        self.wallet = Wallet.objects.create(customer=self.customer)
        self.token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id)
        )

    def test_grants_list_speaks_the_envelope(self):
        from apps.billing.wallets.models import CreditGrant

        for i in range(3):
            CreditGrant.objects.create(
                tenant=self.tenant, wallet=self.wallet, kind="promo",
                granted_micros=1_000_000, remaining_micros=1_000_000,
                currency="usd", status="active", source="test")

        first = self.http_client.get(
            "/api/v1/me/grants?limit=2",
            HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(first.status_code, 200)
        body = first.json()
        self.assertEqual(set(body), {"data", "next_cursor", "has_more"})
        self.assertEqual(len(body["data"]), 2)
        self.assertTrue(body["has_more"])

        second = self.http_client.get(
            f"/api/v1/me/grants?limit=2&cursor={body['next_cursor']}",
            HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(len(second.json()["data"]), 1)
        self.assertFalse(second.json()["has_more"])

    def test_bad_cursor_is_a_400_problem(self):
        response = self.http_client.get(
            "/api/v1/me/grants?cursor=garbage",
            HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response["Content-Type"], "application/problem+json")
        self.assertEqual(response.json()["code"], "invalid_cursor")


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
