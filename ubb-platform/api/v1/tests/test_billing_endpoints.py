import json
from unittest.mock import patch

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.platform.runs.models import Run
from apps.billing.wallets.models import Wallet
from apps.billing.tenant_billing.models import BillingTenantConfig


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
            name="Has Billing", products=["metering", "billing"]
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
            name="Debit Tenant", products=["metering", "billing"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(
            self.tenant, label="test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_debit_1"
        )
        # Give the wallet some balance
        self.wallet = Wallet.objects.create(customer=self.customer)
        self.wallet.balance_micros = 10_000_000
        self.wallet.save()

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
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 7_000_000)

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
        from apps.billing.wallets.models import WalletTransaction
        txn = WalletTransaction.objects.get(id=body["transaction_id"])
        self.assertEqual(txn.transaction_type, "DEBIT")
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
            name="Other Tenant", products=["metering", "billing"]
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
            name="Credit Tenant", products=["metering", "billing"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(
            self.tenant, label="test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_credit_1"
        )
        # Start with zero balance
        self.wallet = Wallet.objects.create(customer=self.customer)

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
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 7_000_000)

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
        from apps.billing.wallets.models import WalletTransaction
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
            name="Other Tenant 2", products=["metering", "billing"]
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


class DebitCreditHardeningTest(TestCase):
    """Phase 2 hardening: lazy wallet creation, locking, idempotency."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Hardening Tenant", products=["metering", "billing"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def test_debit_creates_wallet_lazily(self):
        """Debit creates wallet on-the-fly if none exists."""
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="no_wallet_debit"
        )
        # No wallet created — lock_for_billing will create one
        response = self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({
                "customer_id": "no_wallet_debit",
                "amount_micros": 1_000_000,
                "reference": "ref_lazy",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Wallet.objects.filter(customer=customer).exists())

    def test_credit_creates_wallet_lazily(self):
        """Credit creates wallet on-the-fly if none exists."""
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="no_wallet_credit"
        )
        response = self.http_client.post(
            "/api/v1/billing/credit",
            data=json.dumps({
                "customer_id": "no_wallet_credit",
                "amount_micros": 5_000_000,
                "source": "promo",
                "reference": "ref_lazy",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        wallet = Wallet.objects.get(customer=customer)
        self.assertEqual(wallet.balance_micros, 5_000_000)

    def test_debit_idempotency_prevents_duplicate(self):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="idemp_debit"
        )
        Wallet.objects.create(customer=customer, balance_micros=10_000_000)

        payload = json.dumps({
            "customer_id": "idemp_debit",
            "amount_micros": 2_000_000,
            "reference": "ref_1",
            "idempotency_key": "debit_idem_1",
        })
        resp1 = self.http_client.post(
            "/api/v1/billing/debit", data=payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        resp2 = self.http_client.post(
            "/api/v1/billing/debit", data=payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)
        # Same transaction ID returned
        self.assertEqual(resp1.json()["transaction_id"], resp2.json()["transaction_id"])
        # Only debited once
        wallet = Wallet.objects.get(customer=customer)
        self.assertEqual(wallet.balance_micros, 8_000_000)

    def test_credit_idempotency_prevents_duplicate(self):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="idemp_credit"
        )
        Wallet.objects.create(customer=customer, balance_micros=0)

        payload = json.dumps({
            "customer_id": "idemp_credit",
            "amount_micros": 3_000_000,
            "source": "promo",
            "reference": "ref_1",
            "idempotency_key": "credit_idem_1",
        })
        resp1 = self.http_client.post(
            "/api/v1/billing/credit", data=payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        resp2 = self.http_client.post(
            "/api/v1/billing/credit", data=payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp1.json()["transaction_id"], resp2.json()["transaction_id"])
        wallet = Wallet.objects.get(customer=customer)
        self.assertEqual(wallet.balance_micros, 3_000_000)

    def test_debit_under_lock(self):
        """Verify debit creates a proper WalletTransaction with lock_for_billing."""
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="lock_debit"
        )
        Wallet.objects.create(customer=customer, balance_micros=5_000_000)

        response = self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({
                "customer_id": "lock_debit",
                "amount_micros": 1_000_000,
                "reference": "ref_lock",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        from apps.billing.wallets.models import WalletTransaction
        txn = WalletTransaction.objects.get(wallet__customer=customer)
        self.assertEqual(txn.transaction_type, "DEBIT")
        self.assertEqual(txn.balance_after_micros, 4_000_000)


class WithdrawOutboxEventTest(TestCase):
    """Test that the withdraw endpoint emits a WithdrawalRequested outbox event."""

    def setUp(self):
        from apps.platform.events.models import OutboxEvent
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Withdraw Tenant", products=["metering", "billing"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(
            self.tenant, label="test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_withdraw_1"
        )
        self.wallet = Wallet.objects.create(
            customer=self.customer, balance_micros=10_000_000
        )

    def _withdraw(self, amount_micros=1_000_000, idempotency_key="wdraw_1"):
        return self.http_client.post(
            f"/api/v1/billing/customers/{self.customer.id}/withdraw",
            data=json.dumps({
                "amount_micros": amount_micros,
                "idempotency_key": idempotency_key,
                "description": "Test withdrawal",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

    def test_withdraw_emits_outbox_event(self):
        from apps.platform.events.models import OutboxEvent
        response = self._withdraw()
        self.assertEqual(response.status_code, 200)

        events = OutboxEvent.objects.filter(event_type="billing.withdrawal_requested")
        self.assertEqual(events.count(), 1)
        evt = events.first()
        self.assertEqual(evt.payload["customer_id"], str(self.customer.id))
        self.assertEqual(evt.payload["amount_micros"], 1_000_000)
        self.assertEqual(evt.payload["idempotency_key"], "wdraw_1")
        self.assertEqual(str(evt.tenant_id), str(self.tenant.id))

    def test_withdraw_idempotent_no_duplicate_event(self):
        from apps.platform.events.models import OutboxEvent
        self._withdraw(idempotency_key="wdraw_dup")
        self._withdraw(idempotency_key="wdraw_dup")

        events = OutboxEvent.objects.filter(event_type="billing.withdrawal_requested")
        self.assertEqual(events.count(), 1)

    def test_withdraw_insufficient_balance_no_event(self):
        from apps.platform.events.models import OutboxEvent
        response = self._withdraw(amount_micros=99_000_000)
        self.assertEqual(response.status_code, 400)

        events = OutboxEvent.objects.filter(event_type="billing.withdrawal_requested")
        self.assertEqual(events.count(), 0)


class PreCheckRunTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Run Tenant",
            products=["metering", "billing"],
            run_cost_limit_micros=10_000_000,
            hard_stop_balance_micros=-5_000_000,
        )
        BillingTenantConfig.objects.create(
            tenant=self.tenant,
            run_cost_limit_micros=10_000_000,
            hard_stop_balance_micros=-5_000_000,
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_run_1"
        )
        self.wallet = Wallet.objects.create(
            customer=self.customer, balance_micros=20_000_000
        )

    def _pre_check(self, **extra):
        data = {"customer_id": str(self.customer.id)}
        data.update(extra)
        return self.http_client.post(
            "/api/v1/billing/pre-check",
            data=json.dumps(data),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

    def test_pre_check_start_run_returns_run_id(self):
        resp = self._pre_check(start_run=True)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["allowed"])
        self.assertIsNotNone(body["run_id"])
        self.assertEqual(body["cost_limit_micros"], 10_000_000)
        self.assertEqual(body["hard_stop_balance_micros"], -5_000_000)

        # Run exists in DB
        run = Run.objects.get(id=body["run_id"])
        self.assertEqual(run.status, "active")
        self.assertEqual(run.balance_snapshot_micros, 20_000_000)

    def test_pre_check_start_run_denied_no_run_created(self):
        self.wallet.balance_micros = -6_000_000
        self.wallet.save()

        resp = self._pre_check(start_run=True)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["allowed"])
        self.assertIsNone(body["run_id"])
        self.assertEqual(Run.objects.count(), 0)

    def test_pre_check_without_start_run_returns_null_run(self):
        resp = self._pre_check()
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["allowed"])
        self.assertIsNone(body["run_id"])


class TopUpWithoutConnectorTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        # Tenant WITHOUT Stripe connector
        self.tenant = Tenant.objects.create(
            name="No Stripe", products=["metering", "billing"],
            stripe_connected_account_id="",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_no_stripe",
        )

    def test_topup_emits_event_when_no_stripe_account(self):
        from apps.platform.events.models import OutboxEvent

        response = self.http_client.post(
            f"/api/v1/billing/customers/{self.customer.id}/top-up",
            data=json.dumps({
                "amount_micros": 20_000_000,
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["status"], "topup_requested")

        event = OutboxEvent.objects.filter(
            event_type="billing.topup_requested"
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.payload["amount_micros"], 20_000_000)
        self.assertEqual(event.payload["trigger"], "manual")


class TopUpWithConnectorTest(TestCase):
    """Verify that top-up with Stripe connector still works (existing behavior)."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Has Stripe", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_stripe",
            stripe_customer_id="cus_test",
        )

    @patch("api.v1.billing_endpoints.create_checkout_session")
    def test_topup_creates_checkout_session_when_stripe_active(self, mock_checkout):
        mock_checkout.return_value = "https://checkout.stripe.com/test"

        response = self.http_client.post(
            f"/api/v1/billing/customers/{self.customer.id}/top-up",
            data=json.dumps({
                "amount_micros": 20_000_000,
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["checkout_url"], "https://checkout.stripe.com/test")

    def test_topup_returns_400_when_no_stripe_customer_id(self):
        # Customer without stripe_customer_id
        customer_no_stripe = Customer.objects.create(
            tenant=self.tenant, external_id="no_cus_id",
        )

        response = self.http_client.post(
            f"/api/v1/billing/customers/{customer_no_stripe.id}/top-up",
            data=json.dumps({
                "amount_micros": 20_000_000,
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

        self.assertEqual(response.status_code, 400)
