import json
from datetime import date
from django.test import TestCase, Client
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.invoicing.models import CustomerUsageInvoice
from apps.subscriptions.models import SubscriptionInvoice
from core.widget_auth import create_widget_token
from apps.platform.tenants.tests._rails import RailActivated
from apps.subscriptions.tests._helpers import a_mirrored_subscription


class WidgetTopUpNoWalletSubjectTest(RailActivated, TestCase):
    """Stage A of the pre-Ash billing readiness (2026-11-02): `/me/top-up` is
    the widget twin of the tenant top-up and passes through the same door
    (`api/v1/topups.py :: start_top_up`), so an end customer of a tenant
    whose billing mode holds no wallet — `external + billing`, `postpaid +
    billing` — is refused by name before any attempt row or outbox event
    lands, and the detail names the mode, not the product. The rail is asked
    for by name because `postpaid` is a money mode."""

    def setUp(self):
        self.http_client = Client()
        self.postures = {}
        for mode in ("external", "postpaid"):
            tenant = Tenant.objects.create(
                name=mode, stripe_connected_account_id="",
                products=["metering", "billing"], billing_mode=mode)
            customer = Customer.objects.create(tenant=tenant, external_id=f"c_{mode}")
            token = create_widget_token(
                tenant.widget_secret, str(customer.id), str(tenant.id))
            self.postures[mode] = (tenant, customer, token)

    def test_a_widget_top_up_where_no_wallet_is_held_is_refused_and_registers_nothing(self):
        from apps.billing.topups.models import TopUpAttempt
        from apps.platform.events.models import OutboxEvent
        for mode, (tenant, customer, token) in self.postures.items():
            with self.subTest(mode=mode):
                response = self.http_client.post(
                    "/api/v1/me/top-up",
                    data=json.dumps({
                        "amount_micros": 10_000_000,
                        "success_url": "https://x.test/s",
                        "cancel_url": "https://x.test/c",
                        "idempotency_key": f"w_{mode}",
                    }),
                    content_type="application/json",
                    HTTP_AUTHORIZATION=f"Bearer {token}",
                )
                self.assertEqual(response.status_code, 403, response.content)
                self.assertEqual(response["Content-Type"], "application/problem+json")
                body = response.json()
                self.assertEqual(body["code"], "feature_not_enabled")
                self.assertEqual(
                    body["detail"],
                    "wallet operations are not available in this tenant's "
                    f"billing mode ({mode})")
                self.assertFalse(TopUpAttempt.objects.filter(customer=customer).exists())
                self.assertFalse(OutboxEvent.objects.filter(tenant_id=tenant.id).exists())
                self.assertFalse(Wallet.all_objects.filter(customer=customer).exists())

    def test_me_wallet_reads_refuse_where_no_wallet_is(self):
        """R10 Stage C5 (F-12): the widget's wallet-only READS — balance,
        grants, transactions — are refused by the same door as its writes
        where the tenant's billing mode holds no wallet (`external`,
        `postpaid`): `feature_not_enabled` naming the mode, never a zero
        balance that would invent the wallet the writes refuse."""
        for mode, (tenant, customer, token) in self.postures.items():
            for path in ("/api/v1/me/balance", "/api/v1/me/grants",
                         "/api/v1/me/transactions"):
                with self.subTest(mode=mode, path=path):
                    response = self.http_client.get(
                        path, HTTP_AUTHORIZATION=f"Bearer {token}")
                    self.assertEqual(response.status_code, 403, response.content)
                    self.assertEqual(response["Content-Type"], "application/problem+json")
                    body = response.json()
                    self.assertEqual(body["code"], "feature_not_enabled")
                    self.assertEqual(
                        body["detail"],
                        "wallet operations are not available in this tenant's "
                        f"billing mode ({mode})")
                    self.assertFalse(Wallet.all_objects.filter(customer=customer).exists())


class WidgetBalanceTest(RailActivated, TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            products=["metering", "billing"],
            billing_mode="prepaid",  # the wallet holder (R10 Stage C5, F-12)
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


class WidgetPooledSeatBalanceTest(RailActivated, TestCase):
    """Task 9 finding B: a pooled seat's own wallet can never exist (Task
    8c's lock_for_billing ratchet refuses one), and every top-up this seat
    makes credits the business owner's wallet (start_top_up pins
    billing_owner_id to resolve_billing_owner()). Pre-fix, /me/balance read
    Wallet.objects.get(customer=<the seat>) and 404'd into a fabricated
    balance_micros: 0 that never changed no matter how much the seat
    actually topped up."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            products=["metering", "billing"],
            billing_mode="prepaid",  # the wallet holder (R10 Stage C5, F-12)
        )
        self.business = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business",
            billing_topology="pooled",
        )
        self.seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat1", account_type="seat",
            parent=self.business,
        )
        # The pool's money lives on the BUSINESS wallet, credited by a
        # top-up some seat (not necessarily this one) made.
        self.wallet = Wallet.objects.create(customer=self.business)
        self.wallet.balance_micros = 50_000_000
        self.wallet.save()
        self.token = create_widget_token(
            self.tenant.widget_secret, str(self.seat.id), str(self.tenant.id)
        )

    def test_pooled_seat_balance_reflects_the_owners_wallet(self):
        response = self.http_client.get(
            "/api/v1/me/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        # Pre-fix this was 0 forever — the seat's own wallet row can never
        # exist, so Wallet.objects.get(customer=seat) always 404'd.
        self.assertEqual(body["balance_micros"], 50_000_000)
        self.assertTrue(body["is_pooled_seat"])
        self.assertEqual(body["billing_owner_external_id"], "biz")

    def test_non_pooled_customer_balance_discloses_self_ownership(self):
        individual = Customer.objects.create(
            tenant=self.tenant, external_id="indiv1", account_type="individual",
        )
        Wallet.objects.create(customer=individual, balance_micros=1_000_000)
        token = create_widget_token(
            self.tenant.widget_secret, str(individual.id), str(self.tenant.id)
        )
        response = self.http_client.get(
            "/api/v1/me/balance",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["is_pooled_seat"])
        self.assertEqual(body["billing_owner_external_id"], "indiv1")

    def test_pooled_seat_grants_and_transactions_stay_seat_scoped(self):
        # Deliberately unchanged (Task 9 finding B reasoning): these are
        # itemized lists, not an aggregate number, so they stay seat-scoped
        # and answer an honest empty page rather than the shared ledger.
        grants_resp = self.http_client.get(
            "/api/v1/me/grants",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(grants_resp.status_code, 200)
        self.assertEqual(grants_resp.json()["data"], [])

        txn_resp = self.http_client.get(
            "/api/v1/me/transactions",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(txn_resp.status_code, 200)
        self.assertEqual(txn_resp.json()["data"], [])


class WidgetTransactionsTest(RailActivated, TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            products=["metering", "billing"],
            billing_mode="prepaid",  # the wallet holder (R10 Stage C5, F-12)
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
                transaction_type="top_up",
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


class WidgetTopUpReplayTest(RailActivated, TestCase):
    """#78: widget top-up carries a required idempotency_key; a replay never
    mints a second attempt or re-emits the event (connector-less branch)."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="No Stripe", stripe_connected_account_id="",
            products=["metering", "billing"], billing_mode="prepaid",
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
                event_type="top_up.requested").count(), 1)


class WidgetGrantsEnvelopeTest(RailActivated, TestCase):
    """#78: the /me grants list adopts the one cursor envelope."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Grants", products=["metering", "billing"],
            billing_mode="prepaid",  # the wallet holder (R10 Stage C5, F-12)
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
                currency="usd", status="active", source="other")

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
    sub = a_mirrored_subscription(
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
        customer=customer, billing_owner=customer,
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
        # ONE SHAPE ACROSS THE THREE USAGE-INVOICE ROUTES (R10 Stage C5,
        # F-15): the /me row carries the shared base — including the
        # customer's identity, the currency, the status and when the row was
        # made — and never the operator's push bookkeeping.
        self.assertEqual(row["customer_id"], str(business.id))
        self.assertEqual(row["external_id"], "biz")
        self.assertEqual(row["currency"], "usd")
        self.assertEqual(row["status"], "pushed")
        self.assertIsNotNone(row["created_at"])
        self.assertNotIn("push_attempts", row)
        self.assertNotIn("last_attempt_error", row)

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
