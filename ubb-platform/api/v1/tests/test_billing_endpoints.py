import json
import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.billing.topups.models import AutoTopUpConfig
from apps.billing.wallets.models import Wallet
from apps.platform.tenants.tests._rails import RailActivated
from apps.metering.usage.tests._helpers import a_posting


class BillingProductGatingTest(RailActivated, TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant_no_billing = Tenant.objects.create(
            name="No Billing", products=["metering"]
        )
        self.key_obj_no, self.raw_key_no = TenantApiKey.create_key(
            self.tenant_no_billing, label="test"
        )
        self.tenant_with_billing = Tenant.objects.create(
            name="Has Billing", products=["metering", "billing"],
            # The wallet-only reads below (balance, transactions) answer only
            # where a wallet is held (R10 Stage C5, F-12).
            billing_mode="prepaid",
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

    def test_tenant_without_billing_gets_403_on_the_affordability_question(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer_no.id}/affordability",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_no}",
        )
        self.assertEqual(response.status_code, 403)

    def test_tenant_with_billing_can_ask_the_affordability_question(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer_yes.id}/affordability",
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

    # The billing-mount duplicates of tenant billing-periods/invoices were
    # removed in the Stage-5 final sweep (#86); the canonical routes on the
    # tenant mount (which do not gate on the billing product) are covered by
    # test_tenant_endpoints.py.


class BillingDebitEndpointTest(RailActivated, TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Debit Tenant", products=["metering", "billing"],
            billing_mode="prepaid",  # the wallet holder (Stage A, 2026-11-02)
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
                "customer_id": str(self.customer.id),
                "amount_micros": 1_500_000,
                "reference": "evt_123",
                "idempotency_key": "idem_evt_123",
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
                "customer_id": str(self.customer.id),
                "amount_micros": 3_000_000,
                "reference": "evt_456",
                "idempotency_key": "idem_evt_456",
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
                "customer_id": str(self.customer.id),
                "amount_micros": 2_000_000,
                "reference": "evt_789",
                "idempotency_key": "idem_evt_789",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        body = response.json()
        from apps.billing.wallets.models import WalletTransaction
        txn = WalletTransaction.objects.get(id=body["transaction_id"])
        self.assertEqual(txn.transaction_type, "debit")
        self.assertEqual(txn.amount_micros, -2_000_000)
        self.assertEqual(txn.reference_id, "evt_789")
        self.assertEqual(txn.description, "External debit")

    def test_debit_unknown_customer_returns_404(self):
        response = self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({
                "customer_id": str(uuid.uuid4()),
                "amount_micros": 1_000_000,
                "reference": "ref_1",
                "idempotency_key": "idem_d_ref_1",
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
                "customer_id": str(self.customer.id),
                "amount_micros": 500_000,
                "reference": "ref_2",
                "idempotency_key": "idem_d_ref_2",
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
                "customer_id": str(self.customer.id),
                "amount_micros": 500_000,
                "reference": "ref_3",
                "idempotency_key": "idem_d_ref_3",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    # --- floor guard (Phase 1): debit respects the overdraft floor by default ---

    def _debit(self, customer, amount, key, allow_negative=None):
        body = {"customer_id": str(customer.id), "amount_micros": amount,
                "reference": "od", "idempotency_key": key}
        if allow_negative is not None:
            body["allow_negative"] = allow_negative
        return self.http_client.post(
            "/api/v1/billing/debit", data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def test_debit_blocked_when_it_would_overdraw(self):
        c = Customer.objects.create(tenant=self.tenant, external_id="od_1")
        Wallet.objects.create(customer=c, balance_micros=1_000_000)
        resp = self._debit(c, 2_000_000, "od_k1")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp["Content-Type"], "application/problem+json")
        body = resp.json()
        self.assertEqual(body["code"], "would_overdraw")
        self.assertEqual(body["floor_micros"], 0)
        self.assertEqual(body["balance_micros"], 1_000_000)
        self.assertEqual(Wallet.objects.get(customer=c).balance_micros, 1_000_000)

    def test_debit_allow_negative_forces_overdraw(self):
        c = Customer.objects.create(tenant=self.tenant, external_id="od_2")
        Wallet.objects.create(customer=c, balance_micros=1_000_000)
        resp = self._debit(c, 2_000_000, "od_k2", allow_negative=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Wallet.objects.get(customer=c).balance_micros, -1_000_000)

    def test_debit_within_overdraft_cushion_allowed(self):
        from apps.billing.wallets.models import CustomerBillingProfile
        c = Customer.objects.create(tenant=self.tenant, external_id="od_3")
        Wallet.objects.create(customer=c, balance_micros=1_000_000)
        CustomerBillingProfile.objects.create(customer=c, min_balance_micros=5_000_000)
        resp = self._debit(c, 3_000_000, "od_k3")  # -> -2M, floor -5M: allowed
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Wallet.objects.get(customer=c).balance_micros, -2_000_000)

    def test_debit_where_no_wallet_is_held_is_refused_at_the_boundary(self):
        """The manual-debit matrix's route-level no-wallet row (Stage A of
        the pre-Ash billing readiness, 2026-11-02): a tenant that leaves
        `prepaid` for `postpaid` holds no wallet, so a hand-moved debit —
        even a forced one — is refused by name, and the wallet row it would
        have driven negative is never made. (This replaced a pin that let a
        postpaid debit skip the floor onto a wallet the mode never held.)"""
        self.tenant.billing_mode = "postpaid"
        self.tenant.save()
        c = Customer.objects.create(tenant=self.tenant, external_id="od_4")
        resp = self._debit(c, 1_000_000, "od_k4", allow_negative=True)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp["Content-Type"], "application/problem+json")
        body = resp.json()
        self.assertEqual(body["code"], "feature_not_enabled")
        self.assertEqual(
            body["detail"],
            "wallet operations are not available in this tenant's billing mode (postpaid)")
        self.assertFalse(Wallet.all_objects.filter(customer=c).exists())

    # --- attribution (Phase 1): movement_reason + actor stored on the ledger ---

    def test_debit_records_movement_reason_and_actor(self):
        from apps.billing.wallets.models import WalletTransaction
        resp = self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({"customer_id": str(self.customer.id), "amount_micros": 1_000_000,
                             "reference": "adj", "idempotency_key": "attr_k1",
                             "movement_reason": "correction", "actor": "ops@acme.co"}),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(resp.status_code, 200)
        txn = WalletTransaction.objects.get(id=resp.json()["transaction_id"])
        self.assertEqual(txn.movement_reason, "correction")
        self.assertEqual(txn.actor, "ops@acme.co")

    def test_debit_rejects_unknown_movement_reason(self):
        resp = self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({"customer_id": str(self.customer.id), "amount_micros": 1_000_000,
                             "reference": "adj", "idempotency_key": "attr_k2",
                             "movement_reason": "bogus"}),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(resp.status_code, 422)


class BillingCreditEndpointTest(RailActivated, TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Credit Tenant", products=["metering", "billing"],
            billing_mode="prepaid",
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
                "customer_id": str(self.customer.id),
                "amount_micros": 5_000_000,
                "source": "manual_adjustment",
                "reference": "adj_001",
                "idempotency_key": "idem_adj_001",
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
                "customer_id": str(self.customer.id),
                "amount_micros": 7_000_000,
                "source": "promo",
                "reference": "promo_001",
                "idempotency_key": "idem_promo_001",
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
                "customer_id": str(self.customer.id),
                "amount_micros": 3_000_000,
                "source": "goodwill",
                "reference": "gw_001",
                "idempotency_key": "idem_gw_001",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        body = response.json()
        from apps.billing.wallets.models import WalletTransaction
        txn = WalletTransaction.objects.get(id=body["transaction_id"])
        self.assertEqual(txn.transaction_type, "adjustment")
        self.assertEqual(txn.amount_micros, 3_000_000)
        self.assertEqual(txn.reference_id, "gw_001")
        self.assertEqual(txn.description, "Credit: goodwill")

    def test_credit_unknown_customer_returns_404(self):
        response = self.http_client.post(
            "/api/v1/billing/credit",
            data=json.dumps({
                "customer_id": str(uuid.uuid4()),
                "amount_micros": 1_000_000,
                "source": "test",
                "reference": "ref_1",
                "idempotency_key": "idem_c_ref_1",
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
                "customer_id": str(self.customer.id),
                "amount_micros": 500_000,
                "source": "test",
                "reference": "ref_2",
                "idempotency_key": "idem_c_ref_2",
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
                "customer_id": str(self.customer.id),
                "amount_micros": 500_000,
                "source": "test",
                "reference": "ref_3",
                "idempotency_key": "idem_c_ref_3",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_credit_records_movement_reason_and_actor(self):
        from apps.billing.wallets.models import WalletTransaction
        response = self.http_client.post(
            "/api/v1/billing/credit",
            data=json.dumps({"customer_id": str(self.customer.id), "amount_micros": 1_000_000,
                             "source": "manual", "reference": "adj",
                             "idempotency_key": "attr_c1",
                             "movement_reason": "goodwill", "actor": "ops@acme.co"}),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(response.status_code, 200)
        txn = WalletTransaction.objects.get(id=response.json()["transaction_id"])
        self.assertEqual(txn.movement_reason, "goodwill")
        self.assertEqual(txn.actor, "ops@acme.co")


class DebitCreditHardeningTest(RailActivated, TestCase):
    """Phase 2 hardening: lazy wallet creation, locking, idempotency."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Hardening Tenant", products=["metering", "billing"],
            billing_mode="prepaid",
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
                "customer_id": str(customer.id),
                "amount_micros": 1_000_000,
                "reference": "ref_lazy",
                "idempotency_key": "idem_d_lazy",
                "allow_negative": True,
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
                "customer_id": str(customer.id),
                "amount_micros": 5_000_000,
                "source": "promo",
                "reference": "ref_lazy",
                "idempotency_key": "idem_c_lazy",
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
            "customer_id": str(customer.id),
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
            "customer_id": str(customer.id),
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
                "customer_id": str(customer.id),
                "amount_micros": 1_000_000,
                "reference": "ref_lock",
                "idempotency_key": "idem_ref_lock",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        from apps.billing.wallets.models import WalletTransaction
        txn = WalletTransaction.objects.get(wallet__customer=customer)
        self.assertEqual(txn.transaction_type, "debit")
        self.assertEqual(txn.balance_after_micros, 4_000_000)

    def test_debit_requires_idempotency_key(self):
        customer = Customer.objects.create(tenant=self.tenant, external_id="need_key_d")
        resp = self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({"customer_id": str(customer.id), "amount_micros": 1_000_000,
                             "reference": "ref_nokey"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(resp.status_code, 422)

    def test_credit_requires_idempotency_key(self):
        customer = Customer.objects.create(tenant=self.tenant, external_id="need_key_c")
        resp = self.http_client.post(
            "/api/v1/billing/credit",
            data=json.dumps({"customer_id": str(customer.id), "amount_micros": 1_000_000,
                             "source": "x", "reference": "ref_nokey"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(resp.status_code, 422)


class WithdrawOutboxEventTest(RailActivated, TestCase):
    """Test that the withdraw endpoint emits a WithdrawalRequested outbox event."""

    def setUp(self):
        from apps.platform.events.models import OutboxEvent
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Withdraw Tenant", products=["metering", "billing"],
            billing_mode="prepaid",
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

        events = OutboxEvent.objects.filter(event_type="withdrawal.requested")
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

        events = OutboxEvent.objects.filter(event_type="withdrawal.requested")
        self.assertEqual(events.count(), 1)

    def test_withdraw_insufficient_balance_no_event(self):
        from apps.platform.events.models import OutboxEvent
        response = self._withdraw(amount_micros=99_000_000)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response["Content-Type"], "application/problem+json")
        self.assertEqual(response.json()["code"], "insufficient_balance")

        events = OutboxEvent.objects.filter(event_type="withdrawal.requested")
        self.assertEqual(events.count(), 0)


# THE CLASS THAT STOOD HERE TESTED A SIDE EFFECT THIS ROUTE NO LONGER HAS
# (#410). Four cases, all about the unit of work a flag on the retired
# advisory POST (the affordability question since #463, as a GET)
# used to create: that it was born active with the wallet balance
# snapshotted onto it, that a requested ceiling was snapshotted too, that a
# denied answer created nothing, and that the flagless call created
# nothing. Registering work is its own call now, at the root and ungated,
# so all four moved WITH their subject rather than being deleted:
# `api/v1/tests/test_a_start_claims_its_key.py` holds each of them, and
# `TestTodaysCreationPathIsGone` in that module is where *this* route's
# half — that it registers nothing at all any more — is now asserted.


class TopUpWithoutConnectorTest(RailActivated, TestCase):
    def setUp(self):
        self.http_client = Client()
        # Tenant WITHOUT Stripe connector
        self.tenant = Tenant.objects.create(
            name="No Stripe", products=["metering", "billing"],
            stripe_connected_account_id="", billing_mode="prepaid",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_no_stripe",
        )

    def _topup(self, idempotency_key="tp_evt_1"):
        return self.http_client.post(
            f"/api/v1/billing/customers/{self.customer.id}/top-up",
            data=json.dumps({
                "amount_micros": 20_000_000,
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
                "idempotency_key": idempotency_key,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

    def test_topup_emits_event_when_no_stripe_account(self):
        from apps.platform.events.models import OutboxEvent

        response = self._topup()

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["status"], "topup_requested")

        event = OutboxEvent.objects.filter(
            event_type="top_up.requested"
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.payload["amount_micros"], 20_000_000)
        self.assertEqual(event.payload["trigger"], "manual")

    def test_topup_replay_answers_202_without_second_event(self):
        from apps.platform.events.models import OutboxEvent

        first = self._topup(idempotency_key="tp_evt_dup")
        replay = self._topup(idempotency_key="tp_evt_dup")

        self.assertEqual(first.status_code, 202)
        self.assertEqual(replay.status_code, 202)
        self.assertEqual(
            OutboxEvent.objects.filter(
                event_type="top_up.requested").count(),
            1)

    def test_topup_without_idempotency_key_is_a_422_problem(self):
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
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response["Content-Type"], "application/problem+json")
        self.assertEqual(response.json()["code"], "validation_error")


class TopUpAttemptBillingOwnerPinTest(RailActivated, TestCase):
    """Task 7 — create_top_up must pin TopUpAttempt.billing_owner_id at
    creation, across all three topologies. `customer` on the row always
    stays the SEAT (who initiated); this test asserts what actually gets
    pinned into billing_owner_id, the value both credit_top_up call sites
    key on later."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="No Stripe Pin Tenant", products=["metering", "billing"],
            stripe_connected_account_id="", billing_mode="prepaid",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def _topup(self, customer, idempotency_key):
        return self.http_client.post(
            f"/api/v1/billing/customers/{customer.id}/top-up",
            data=json.dumps({
                "amount_micros": 10_000_000,
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
                "idempotency_key": idempotency_key,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

    def test_individual_pins_self(self):
        from apps.billing.topups.models import TopUpAttempt
        customer = Customer.objects.create(tenant=self.tenant, external_id="ind_pin")
        resp = self._topup(customer, "pin_ind_1")
        self.assertEqual(resp.status_code, 202)
        attempt = TopUpAttempt.objects.get(customer=customer)
        self.assertEqual(attempt.billing_owner_id, customer.id)

    def test_pooled_seat_pins_the_business(self):
        from apps.billing.topups.models import TopUpAttempt
        biz = Customer.objects.create(
            tenant=self.tenant, external_id="biz_pin",
            account_type="business", billing_topology="pooled")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat_pin",
            account_type="seat", parent=biz)
        resp = self._topup(seat, "pin_pooled_1")
        self.assertEqual(resp.status_code, 202)
        attempt = TopUpAttempt.objects.get(customer=seat)
        self.assertEqual(attempt.billing_owner_id, biz.id)

    def test_allocated_seat_pins_self(self):
        from apps.billing.topups.models import TopUpAttempt
        biz = Customer.objects.create(
            tenant=self.tenant, external_id="biz_alloc_pin",
            account_type="business", billing_topology="allocated")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat_alloc_pin",
            account_type="seat", parent=biz)
        resp = self._topup(seat, "pin_alloc_1")
        self.assertEqual(resp.status_code, 202)
        attempt = TopUpAttempt.objects.get(customer=seat)
        self.assertEqual(attempt.billing_owner_id, seat.id)


class TopUpWithConnectorTest(RailActivated, TestCase):
    """Verify that top-up with Stripe connector still works (existing behavior).
    "Stripe active" means a connected account that is charge-ready: since C1b
    (F-11) a top-up asks that BEFORE it writes, so the fixture says so."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Has Stripe", products=["metering", "billing"],
            stripe_connected_account_id="acct_test", billing_mode="prepaid",
            charges_enabled=True,
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_stripe",
            stripe_customer_id="cus_test",
        )

    def _topup(self, customer, idempotency_key="tp_chk_1"):
        return self.http_client.post(
            f"/api/v1/billing/customers/{customer.id}/top-up",
            data=json.dumps({
                "amount_micros": 20_000_000,
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
                "idempotency_key": idempotency_key,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

    @patch("api.v1.billing_endpoints.create_checkout_session")
    def test_topup_creates_checkout_session_when_stripe_active(self, mock_checkout):
        mock_checkout.return_value = "https://checkout.stripe.com/test"

        response = self._topup(self.customer)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["checkout_url"], "https://checkout.stripe.com/test")

    @patch("api.v1.billing_endpoints.create_checkout_session")
    def test_topup_replay_reuses_the_attempt(self, mock_checkout):
        from apps.billing.topups.models import TopUpAttempt

        mock_checkout.return_value = "https://checkout.stripe.com/test"

        first = self._topup(self.customer, idempotency_key="tp_chk_dup")
        replay = self._topup(self.customer, idempotency_key="tp_chk_dup")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(
            TopUpAttempt.objects.filter(customer=self.customer).count(), 1)
        # Both calls rendered a session off the SAME attempt (Stripe's own
        # idempotency on checkout-{attempt.id} makes that the same session).
        attempts = {call.args[2].id for call in mock_checkout.call_args_list}
        self.assertEqual(len(attempts), 1)

    def test_topup_is_a_409_problem_when_no_stripe_customer_id(self):
        # Customer without stripe_customer_id
        customer_no_stripe = Customer.objects.create(
            tenant=self.tenant, external_id="no_cus_id",
        )

        response = self._topup(customer_no_stripe)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response["Content-Type"], "application/problem+json")
        self.assertEqual(response.json()["code"], "conflict")


class ATopUpRefusesBeforeItWritesTest(RailActivated, TestCase):
    """R10 Stage C1b (F-11 + O-6, RULED Q2/Q21): every knowable precondition
    of a top-up checkout is evaluated BEFORE the TopUpAttempt and its audit
    row are written, and each refusal is its truthful registered problem. On
    the C1a anchor a tenant whose connected account was not charge-ready got
    a bare 500 `internal_error` from the connector's StripeFatalError, with
    a `pending` attempt and an audit row left behind every time (Stage B
    F-11); a closed rail refused by name but also left the pending attempt
    (O-6)."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Refuses", products=["metering", "billing"],
            stripe_connected_account_id="acct_refuses", billing_mode="prepaid",
            charges_enabled=True,
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_refuses", stripe_customer_id="cus_refuses")

    def _topup(self, idempotency_key="tp_refuse_1", amount=20_000_000):
        return self.http_client.post(
            f"/api/v1/billing/customers/{self.customer.id}/top-up",
            data=json.dumps({
                "amount_micros": amount,
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
                "idempotency_key": idempotency_key,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

    def _zero_rows(self):
        from apps.billing.topups.models import TopUpAttempt
        from apps.platform.audit.models import AuditRecord
        self.assertFalse(TopUpAttempt.objects.filter(customer=self.customer).exists())
        self.assertFalse(AuditRecord.objects.filter(
            tenant_id=self.tenant.id, action="top_up.requested").exists())

    def _problem(self, response, status, code):
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response["Content-Type"], "application/problem+json")
        body = response.json()
        self.assertEqual(body["code"], code)
        return body

    def test_a_connected_account_that_is_not_charge_ready_is_payment_not_available_with_zero_rows(self):
        Tenant.objects.filter(pk=self.tenant.pk).update(charges_enabled=False)
        with patch("apps.billing.connectors.stripe.stripe_api.stripe_call") as stripe_call:
            response = self._topup()
        body = self._problem(response, 409, "payment_not_available")
        self.assertIn("charges_enabled=False", body["detail"])
        stripe_call.assert_not_called()
        self._zero_rows()

    def test_no_connected_account_is_payment_not_available_at_the_connector(self):
        """The route takes the no-connector branch for a tenant with no
        account at all (a legitimate product path: the event hand-off), so
        the "no connected account" refusal is the connector's own, asked by
        anything that calls it directly."""
        from apps.billing.connectors.stripe.stripe_api import (
            refuse_a_checkout_that_cannot_proceed)
        from core.exceptions import PaymentNotAvailable
        Tenant.objects.filter(pk=self.tenant.pk).update(stripe_connected_account_id="")
        self.customer.tenant.refresh_from_db()
        with self.assertRaisesRegex(PaymentNotAvailable, "no connected Stripe account") as ctx:
            refuse_a_checkout_that_cannot_proceed(
                self.customer, 20_000_000, owner_id=self.customer.id)
        self.assertEqual(ctx.exception.code, "payment_not_available")
        self._zero_rows()

    def test_no_server_key_is_service_unavailable_with_zero_rows(self):
        with self.settings(STRIPE_SECRET_KEY=""), \
                patch("apps.billing.connectors.stripe.stripe_api.stripe_call") as stripe_call:
            response = self._topup()
        self._problem(response, 503, "service_unavailable")
        stripe_call.assert_not_called()
        self._zero_rows()

    def test_a_sandbox_tenant_without_a_test_key_is_service_unavailable_with_zero_rows(self):
        from apps.billing.topups.models import TopUpAttempt
        sandbox = Tenant.objects.create(
            name="Refuses sandbox", products=["metering", "billing"],
            billing_mode="prepaid", is_sandbox=True, parent_tenant=self.tenant,
            stripe_connected_account_id="acct_refuses", charges_enabled=True)
        _key_obj, raw_key = TenantApiKey.create_key(sandbox, label="sandbox", is_test=True)
        customer = Customer.objects.create(
            tenant=sandbox, external_id="cust_sandbox", stripe_customer_id="cus_sandbox")
        with self.settings(STRIPE_TEST_SECRET_KEY=""), \
                patch("apps.billing.connectors.stripe.stripe_api.stripe_call") as stripe_call:
            response = self.http_client.post(
                f"/api/v1/billing/customers/{customer.id}/top-up",
                data=json.dumps({
                    "amount_micros": 20_000_000,
                    "success_url": "https://example.com/success",
                    "cancel_url": "https://example.com/cancel",
                    "idempotency_key": "tp_sandbox_no_key",
                }),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {raw_key}",
            )
        self._problem(response, 503, "service_unavailable")
        stripe_call.assert_not_called()
        self.assertFalse(TopUpAttempt.objects.filter(customer=customer).exists())

    def test_a_currency_disagreement_is_the_registered_currency_problem_with_zero_rows(self):
        # The database holds every wallet to USD (ADR-0023), so the record
        # that disagrees is staged at the one seam that names it: the wallet
        # a top-up will credit answers a currency the rail does not admit.
        with patch("apps.billing.connectors.stripe.stripe_api.the_currency_a_top_up_will_credit",
                   return_value=("wallet w_eur", "eur")), \
                patch("apps.billing.connectors.stripe.stripe_api.stripe_call") as stripe_call:
            response = self._topup()
        body = self._problem(response, 422, "unsupported_currency")
        self.assertIn("'eur'", body["detail"])
        stripe_call.assert_not_called()
        self._zero_rows()

    def test_an_invalid_amount_is_a_validation_error_with_zero_rows(self):
        # The request schema refuses it first; the money-boundary rule says
        # the same thing when asked directly.
        from apps.billing.connectors.stripe.stripe_api import (
            refuse_a_checkout_that_cannot_proceed)
        from core.problems import Problem
        response = self._topup(amount=0)
        self._problem(response, 422, "validation_error")
        with self.assertRaises(Problem) as ctx:
            refuse_a_checkout_that_cannot_proceed(self.customer, 0, owner_id=self.customer.id)
        self.assertEqual(ctx.exception.code, "validation_error")
        with self.assertRaises(Problem) as ctx:
            refuse_a_checkout_that_cannot_proceed(self.customer, 15, owner_id=self.customer.id)
        self.assertEqual(ctx.exception.code, "validation_error")
        self._zero_rows()

    def test_a_stripe_refusal_at_session_create_fails_the_attempt_and_is_payment_not_available(self):
        """Only Stripe's own refusal can arrive after the attempt exists: the
        attempt is `failed` with the reason (never left pending), the audit
        row stands (the top-up WAS requested), and the answer is the
        registered problem with the Stripe detail — never `internal_error`."""
        from apps.billing.topups.models import TopUpAttempt
        from apps.platform.audit.models import AuditRecord
        from core.exceptions import StripeFatalError
        with patch("apps.billing.connectors.stripe.stripe_api.stripe_call",
                   side_effect=StripeFatalError("No such customer: 'cus_refuses'")):
            response = self._topup("tp_refused_by_stripe")
        body = self._problem(response, 409, "payment_not_available")
        self.assertEqual(body["detail"], "No such customer: 'cus_refuses'")
        attempt = TopUpAttempt.objects.get(
            customer=self.customer, idempotency_key="tp_refused_by_stripe")
        self.assertEqual(attempt.status, "failed")
        self.assertEqual(attempt.failure_reason["error"], "No such customer: 'cus_refuses'")
        self.assertEqual(attempt.failure_reason["stage"], "checkout_session_create")
        self.assertEqual(AuditRecord.objects.filter(
            tenant_id=self.tenant.id, action="top_up.requested").count(), 1)
        # Replaying the same key starts no second attempt and does not resurrect it.
        with patch("apps.billing.connectors.stripe.stripe_api.stripe_call",
                   side_effect=StripeFatalError("No such customer: 'cus_refuses'")):
            self._problem(self._topup("tp_refused_by_stripe"), 409, "payment_not_available")
        self.assertEqual(TopUpAttempt.objects.filter(customer=self.customer).count(), 1)

    def test_a_transient_upstream_failure_is_service_unavailable_and_the_attempt_stays_pending(self):
        from apps.billing.topups.models import TopUpAttempt
        from core.exceptions import StripeTransientError
        with patch("apps.billing.connectors.stripe.stripe_api.stripe_call",
                   side_effect=StripeTransientError("connection reset")):
            response = self._topup("tp_transient")
        self._problem(response, 503, "service_unavailable")
        self.assertEqual(response["Retry-After"], "60")
        attempt = TopUpAttempt.objects.get(customer=self.customer, idempotency_key="tp_transient")
        self.assertEqual(attempt.status, "pending")
        # The same key then succeeds against a recovered upstream — same attempt.
        import stripe
        session = stripe.checkout.Session.construct_from({
            "id": "cs_recovered", "object": "checkout.session",
            "url": "https://checkout.stripe.com/recovered", "mode": "payment",
            "payment_status": "unpaid"}, "sk_test_sentinel")
        with patch("apps.billing.connectors.stripe.stripe_api.stripe_call",
                   return_value=session):
            ok = self._topup("tp_transient")
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(ok.json()["checkout_url"], "https://checkout.stripe.com/recovered")
        self.assertEqual(TopUpAttempt.objects.filter(customer=self.customer).count(), 1)
        attempt.refresh_from_db()
        self.assertEqual(attempt.stripe_checkout_session_id, "cs_recovered")

    def test_a_key_lost_at_session_create_is_service_unavailable_and_the_attempt_stays_pending(self):
        """The wrapper's own not-configured refusal (the key vanished between
        the precondition and the call) is the service's state, not the
        subject's: 503, the attempt pending for the same key to retry —
        never `failed`, never `payment_not_available`."""
        from apps.billing.topups.models import TopUpAttempt
        from core.exceptions import StripeNotConfigured
        with patch("apps.billing.connectors.stripe.stripe_api.stripe_call",
                   side_effect=StripeNotConfigured("Stripe API key is not configured.")):
            response = self._topup("tp_key_lost")
        self._problem(response, 503, "service_unavailable")
        self.assertEqual(TopUpAttempt.objects.get(
            customer=self.customer, idempotency_key="tp_key_lost").status, "pending")


class TenantUsageInvoicePeriodValidationTest(TestCase):
    """#13 — ?period bad input must return 400, not 500."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Period Test Tenant", products=["metering", "billing"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def _get(self, period):
        return self.http_client.get(
            f"/api/v1/billing/tenant/usage-invoices?period={period}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

    def test_period_non_numeric_returns_400(self):
        response = self._get("abc")
        self.assertEqual(response.status_code, 400)

    def test_period_no_dash_returns_400(self):
        response = self._get("2026")
        self.assertEqual(response.status_code, 400)

    def test_period_month_out_of_range_returns_400(self):
        response = self._get("2026-13")
        self.assertEqual(response.status_code, 400)

    def test_period_month_zero_returns_400(self):
        response = self._get("2026-00")
        self.assertEqual(response.status_code, 400)

    def test_period_valid_returns_200(self):
        response = self._get("2026-06")
        self.assertEqual(response.status_code, 200)


class PooledSeatBillingSurfaceTest(RailActivated, TestCase):
    """Task 3 — uniform billing-owner resolution.

    Covers all three topologies for every touched endpoint:
    - individual customer: owner == self, is_pooled_seat False, unchanged
    - pooled seat: parent business with billing_topology="pooled" — reads
      and money-moving writes must hit the BUSINESS's wallet
    - non-pooled (allocated) seat: parent exists but billing_topology is not
      "pooled" — resolves to self, same as an individual

    The load-bearing assertion throughout is that a pooled seat NEVER grows
    its own wallet/config row — that's the bug this task fixes.
    """

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Pooled Tenant", products=["metering", "billing"],
            billing_mode="prepaid",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

        self.individual = Customer.objects.create(tenant=self.tenant, external_id="ind_1")

        self.pooled_biz = Customer.objects.create(
            tenant=self.tenant, external_id="biz_pooled",
            account_type="business", billing_topology="pooled")
        self.pooled_seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat_pooled",
            account_type="seat", parent=self.pooled_biz)

        self.alloc_biz = Customer.objects.create(
            tenant=self.tenant, external_id="biz_alloc",
            account_type="business", billing_topology="allocated")
        self.alloc_seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat_alloc",
            account_type="seat", parent=self.alloc_biz)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    # ---------- balance ----------

    def test_balance_individual_reports_self_as_owner(self):
        Wallet.objects.create(customer=self.individual, balance_micros=1_000_000)
        r = self.http_client.get(
            f"/api/v1/billing/customers/{self.individual.id}/balance", **self._auth())
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertFalse(b["is_pooled_seat"])
        self.assertEqual(b["billing_owner_id"], str(self.individual.id))
        self.assertEqual(b["billing_owner_external_id"], "ind_1")
        self.assertEqual(b["balance_micros"], 1_000_000)

    def test_balance_pooled_seat_reads_business_wallet(self):
        Wallet.objects.create(customer=self.pooled_biz, balance_micros=5_000_000)
        r = self.http_client.get(
            f"/api/v1/billing/customers/{self.pooled_seat.id}/balance", **self._auth())
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertTrue(b["is_pooled_seat"])
        self.assertEqual(b["billing_owner_id"], str(self.pooled_biz.id))
        self.assertEqual(b["billing_owner_external_id"], "biz_pooled")
        self.assertEqual(b["balance_micros"], 5_000_000)
        self.assertFalse(Wallet.objects.filter(customer=self.pooled_seat).exists())

    def test_balance_pooled_seat_no_wallet_still_reports_owner(self):
        # No wallet on either row: no-wallet fallback branch, still discloses
        # the owner rather than defaulting to the seat.
        r = self.http_client.get(
            f"/api/v1/billing/customers/{self.pooled_seat.id}/balance", **self._auth())
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["balance_micros"], 0)
        self.assertTrue(b["is_pooled_seat"])
        self.assertEqual(b["billing_owner_id"], str(self.pooled_biz.id))

    def test_balance_allocated_seat_resolves_to_self(self):
        Wallet.objects.create(customer=self.alloc_seat, balance_micros=2_000_000)
        r = self.http_client.get(
            f"/api/v1/billing/customers/{self.alloc_seat.id}/balance", **self._auth())
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertFalse(b["is_pooled_seat"])
        self.assertEqual(b["billing_owner_id"], str(self.alloc_seat.id))
        self.assertEqual(b["balance_micros"], 2_000_000)

    # ---------- transactions ----------

    def test_transactions_pooled_seat_reads_business_ledger(self):
        Wallet.objects.create(customer=self.pooled_biz, balance_micros=0)
        from apps.billing.wallets import operations as wallet_ops
        wallet_ops.credit(customer_id=self.pooled_biz.id, tenant=self.tenant,
                          amount_micros=1_000_000, idempotency_key="seed_k1")
        r = self.http_client.get(
            f"/api/v1/billing/customers/{self.pooled_seat.id}/transactions", **self._auth())
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["is_pooled_seat"])
        self.assertEqual(body["billing_owner_id"], str(self.pooled_biz.id))
        self.assertEqual(len(body["data"]), 1)

    def test_transactions_individual_reports_self_and_unchanged_shape(self):
        r = self.http_client.get(
            f"/api/v1/billing/customers/{self.individual.id}/transactions", **self._auth())
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertFalse(b["is_pooled_seat"])
        self.assertEqual(b["billing_owner_id"], str(self.individual.id))
        self.assertEqual(b["data"], [])
        self.assertIn("has_more", b)

    def test_transactions_allocated_seat_resolves_to_self(self):
        r = self.http_client.get(
            f"/api/v1/billing/customers/{self.alloc_seat.id}/transactions", **self._auth())
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertFalse(b["is_pooled_seat"])
        self.assertEqual(b["billing_owner_id"], str(self.alloc_seat.id))

    # ---------- debit ----------

    def test_debit_pooled_seat_moves_business_wallet_no_second_wallet(self):
        Wallet.objects.create(customer=self.pooled_biz, balance_micros=10_000_000)
        r = self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({"customer_id": str(self.pooled_seat.id), "amount_micros": 2_000_000,
                             "reference": "r1", "idempotency_key": "dk1"}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            Wallet.objects.get(customer=self.pooled_biz).balance_micros, 8_000_000)
        # The pin: no second, unread wallet is minted on the seat.
        self.assertFalse(Wallet.objects.filter(customer=self.pooled_seat).exists())

    def test_debit_allocated_seat_unchanged(self):
        Wallet.objects.create(customer=self.alloc_seat, balance_micros=5_000_000)
        r = self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({"customer_id": str(self.alloc_seat.id), "amount_micros": 1_000_000,
                             "reference": "r1", "idempotency_key": "dk_alloc"}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            Wallet.objects.get(customer=self.alloc_seat).balance_micros, 4_000_000)

    def test_debit_audit_keeps_seat_as_subject_and_records_owner(self):
        from apps.platform.audit.models import AuditRecord
        Wallet.objects.create(customer=self.pooled_biz, balance_micros=10_000_000)
        self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({"customer_id": str(self.pooled_seat.id), "amount_micros": 1_000_000,
                             "reference": "r1", "idempotency_key": "dk_audit"}),
            content_type="application/json", **self._auth())
        rec = AuditRecord.objects.get(action="wallet.debited")
        self.assertEqual(rec.resource_id, str(self.pooled_seat.id))
        self.assertEqual(rec.metadata["customer_id"], str(self.pooled_seat.id))
        self.assertEqual(rec.metadata["owner_id"], str(self.pooled_biz.id))

    # ---------- credit ----------

    def test_credit_pooled_seat_moves_business_wallet_no_second_wallet(self):
        r = self.http_client.post(
            "/api/v1/billing/credit",
            data=json.dumps({"customer_id": str(self.pooled_seat.id), "amount_micros": 3_000_000,
                             "source": "manual", "reference": "r1",
                             "idempotency_key": "ck1"}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            Wallet.objects.get(customer=self.pooled_biz).balance_micros, 3_000_000)
        self.assertFalse(Wallet.objects.filter(customer=self.pooled_seat).exists())

    def test_credit_allocated_seat_unchanged(self):
        r = self.http_client.post(
            "/api/v1/billing/credit",
            data=json.dumps({"customer_id": str(self.alloc_seat.id), "amount_micros": 2_000_000,
                             "source": "manual", "reference": "r1",
                             "idempotency_key": "ck_alloc"}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            Wallet.objects.get(customer=self.alloc_seat).balance_micros, 2_000_000)

    def test_credit_audit_keeps_seat_as_subject_and_records_owner(self):
        from apps.platform.audit.models import AuditRecord
        self.http_client.post(
            "/api/v1/billing/credit",
            data=json.dumps({"customer_id": str(self.pooled_seat.id), "amount_micros": 1_000_000,
                             "source": "manual", "reference": "r1",
                             "idempotency_key": "ck_audit"}),
            content_type="application/json", **self._auth())
        rec = AuditRecord.objects.get(action="wallet.credited")
        self.assertEqual(rec.resource_id, str(self.pooled_seat.id))
        self.assertEqual(rec.metadata["customer_id"], str(self.pooled_seat.id))
        self.assertEqual(rec.metadata["owner_id"], str(self.pooled_biz.id))

    # ---------- withdraw ----------

    def test_withdraw_pooled_seat_moves_business_wallet_no_second_wallet(self):
        Wallet.objects.create(customer=self.pooled_biz, balance_micros=10_000_000)
        r = self.http_client.post(
            f"/api/v1/billing/customers/{self.pooled_seat.id}/withdraw",
            data=json.dumps({"amount_micros": 4_000_000, "idempotency_key": "wk1"}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            Wallet.objects.get(customer=self.pooled_biz).balance_micros, 6_000_000)
        self.assertFalse(Wallet.objects.filter(customer=self.pooled_seat).exists())

    def test_withdraw_allocated_seat_unchanged(self):
        Wallet.objects.create(customer=self.alloc_seat, balance_micros=5_000_000)
        r = self.http_client.post(
            f"/api/v1/billing/customers/{self.alloc_seat.id}/withdraw",
            data=json.dumps({"amount_micros": 1_000_000, "idempotency_key": "wk_alloc"}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            Wallet.objects.get(customer=self.alloc_seat).balance_micros, 4_000_000)

    def test_withdraw_audit_keeps_seat_as_subject_and_records_owner(self):
        from apps.platform.audit.models import AuditRecord
        Wallet.objects.create(customer=self.pooled_biz, balance_micros=10_000_000)
        self.http_client.post(
            f"/api/v1/billing/customers/{self.pooled_seat.id}/withdraw",
            data=json.dumps({"amount_micros": 1_000_000, "idempotency_key": "wk_audit"}),
            content_type="application/json", **self._auth())
        rec = AuditRecord.objects.get(action="wallet.withdrawn")
        self.assertEqual(rec.resource_id, str(self.pooled_seat.id))
        self.assertEqual(rec.metadata["customer_id"], str(self.pooled_seat.id))
        self.assertEqual(rec.metadata["owner_id"], str(self.pooled_biz.id))

    # ---------- refund_usage ----------

    def _usage_event(self, customer, amount=1_000_000, correlation="r1"):
        from apps.metering.usage.models import Posting
        return a_posting(
            tenant=self.tenant, customer=customer,
            idempotency_key=f"idem_{correlation}",
            provider_cost_micros=amount, billed_cost_micros=amount)

    def test_refund_pooled_seat_moves_business_wallet_no_second_wallet(self):
        Wallet.objects.create(customer=self.pooled_biz, balance_micros=5_000_000)
        event = self._usage_event(self.pooled_seat, amount=1_000_000)
        r = self.http_client.post(
            f"/api/v1/billing/customers/{self.pooled_seat.id}/refund",
            data=json.dumps({"usage_event_id": str(event.id),
                             "idempotency_key": "rk1"}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            Wallet.objects.get(customer=self.pooled_biz).balance_micros, 6_000_000)
        self.assertFalse(Wallet.objects.filter(customer=self.pooled_seat).exists())

    def test_refund_allocated_seat_unchanged(self):
        Wallet.objects.create(customer=self.alloc_seat, balance_micros=5_000_000)
        event = self._usage_event(self.alloc_seat, amount=1_000_000)
        r = self.http_client.post(
            f"/api/v1/billing/customers/{self.alloc_seat.id}/refund",
            data=json.dumps({"usage_event_id": str(event.id),
                             "idempotency_key": "rk_alloc"}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            Wallet.objects.get(customer=self.alloc_seat).balance_micros, 6_000_000)

    def test_refund_individual_unchanged(self):
        Wallet.objects.create(customer=self.individual, balance_micros=5_000_000)
        event = self._usage_event(self.individual, amount=1_000_000)
        r = self.http_client.post(
            f"/api/v1/billing/customers/{self.individual.id}/refund",
            data=json.dumps({"usage_event_id": str(event.id),
                             "idempotency_key": "rk_ind"}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            Wallet.objects.get(customer=self.individual).balance_micros, 6_000_000)

    def test_refunding_an_unpriced_posting_says_so_rather_than_not_found(self):
        """⚠ THE REFUSAL CODE IS READ AT THE ROUTE, NOT COLLAPSED (#351).

        The wallet seam gained a second refusal when the customer price column
        went nullable, and this route mapped EVERY refusal to
        `not_found` — so a posting that plainly exists, and whose price UBB
        could not resolve, would have been reported to the tenant as a posting
        that does not exist. They would go looking for a record sitting right
        there.

        Asserted THROUGH THE ROUTE rather than at the seam, because the seam was
        already right: the defect lived entirely in the collapse, and a test of
        `refund_usage` would have passed throughout.
        """
        from apps.metering.usage.models import Posting
        from core.vocabulary import PRICING_STATUS_UNKNOWN

        Wallet.objects.create(customer=self.individual, balance_micros=5_000_000)
        event = a_posting(
            tenant=self.tenant, customer=self.individual,
            idempotency_key="idem_r_unpriced", provider_cost_micros=1_000,
            billed_cost_micros=None, pricing_status=PRICING_STATUS_UNKNOWN)

        r = self.http_client.post(
            f"/api/v1/billing/customers/{self.individual.id}/refund",
            data=json.dumps({"usage_event_id": str(event.id),
                             "idempotency_key": "rk_unpriced"}),
            content_type="application/json", **self._auth())

        self.assertEqual(r.status_code, 409)
        body = r.json()
        self.assertEqual(body["code"], "conflict")
        self.assertIn("no resolved customer price", body["detail"])
        # And the wallet did not move, which is the thing the refusal is for.
        self.assertEqual(
            Wallet.objects.get(customer=self.individual).balance_micros, 5_000_000)

    def test_refunding_a_posting_that_really_is_absent_still_says_not_found(self):
        """The other arm, and the reason the branch above is not a rename.

        Without this, mapping every refusal to `conflict` would pass the test
        above just as well — and the two answers would have swapped rather than
        separated.
        """
        import uuid as _uuid
        Wallet.objects.create(customer=self.individual, balance_micros=5_000_000)
        r = self.http_client.post(
            f"/api/v1/billing/customers/{self.individual.id}/refund",
            data=json.dumps({"usage_event_id": str(_uuid.uuid4()),
                             "idempotency_key": "rk_absent"}),
            content_type="application/json", **self._auth())

        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["code"], "not_found")

    def test_refund_audit_keeps_seat_as_subject_and_records_owner(self):
        from apps.platform.audit.models import AuditRecord
        Wallet.objects.create(customer=self.pooled_biz, balance_micros=5_000_000)
        event = self._usage_event(self.pooled_seat, amount=1_000_000)
        self.http_client.post(
            f"/api/v1/billing/customers/{self.pooled_seat.id}/refund",
            data=json.dumps({"usage_event_id": str(event.id),
                             "idempotency_key": "rk_audit"}),
            content_type="application/json", **self._auth())
        rec = AuditRecord.objects.get(action="usage.refunded")
        self.assertEqual(rec.resource_id, str(self.pooled_seat.id))
        self.assertEqual(rec.metadata["customer_id"], str(self.pooled_seat.id))
        self.assertEqual(rec.metadata["owner_id"], str(self.pooled_biz.id))

    # ---------- configure_auto_top_up ----------

    def test_configure_auto_top_up_pooled_seat_configures_business_only(self):
        r = self.http_client.put(
            f"/api/v1/billing/customers/{self.pooled_seat.id}/auto-top-up",
            data=json.dumps({"is_enabled": True, "trigger_threshold_micros": 1_000_000,
                             "top_up_amount_micros": 5_000_000}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertTrue(
            AutoTopUpConfig.objects.filter(customer=self.pooled_biz, is_enabled=True).exists())
        self.assertFalse(AutoTopUpConfig.objects.filter(customer=self.pooled_seat).exists())

    def test_configure_auto_top_up_allocated_seat_unchanged(self):
        r = self.http_client.put(
            f"/api/v1/billing/customers/{self.alloc_seat.id}/auto-top-up",
            data=json.dumps({"is_enabled": True, "trigger_threshold_micros": 1_000_000,
                             "top_up_amount_micros": 5_000_000}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertTrue(
            AutoTopUpConfig.objects.filter(customer=self.alloc_seat, is_enabled=True).exists())

    def test_configure_auto_top_up_audit_keeps_seat_as_subject_and_records_owner(self):
        from apps.platform.audit.models import AuditRecord
        self.http_client.put(
            f"/api/v1/billing/customers/{self.pooled_seat.id}/auto-top-up",
            data=json.dumps({"is_enabled": True, "trigger_threshold_micros": 1_000_000,
                             "top_up_amount_micros": 5_000_000}),
            content_type="application/json", **self._auth())
        rec = AuditRecord.objects.get(action="auto_top_up.configured")
        self.assertEqual(rec.resource_id, str(self.pooled_seat.id))
        self.assertEqual(rec.metadata["customer_id"], str(self.pooled_seat.id))
        self.assertEqual(rec.metadata["owner_id"], str(self.pooled_biz.id))


class NoWalletSubjectRoutesTest(RailActivated, TestCase):
    """Stage A of the pre-Ash billing readiness (owner/consultant rulings of
    2026-11-02): a wallet exists only where `holds_a_wallet(tenant)` is true.
    Every wallet-mutating route answers a tenant whose billing mode holds no
    wallet — `external + billing` and `postpaid + billing`, both valid
    postures — with the registered `feature_not_enabled` problem (403) and a
    detail that names the MODE the wallet capability is absent in, never the
    product the tenant holds; and it writes nothing: no Wallet,
    WalletTransaction, CreditGrant, WalletReservation, TopUpAttempt or
    AutoTopUpConfig row, and no outbox event. The non-wallet billing surface
    the product brings stays: the customer spend pool, the postpaid
    configuration, the affordability read. `prepaid` keeps every behaviour
    the classes above pin. The rail is asked for by name (`RailActivated`)
    because `postpaid` is a money mode.
    """

    DETAIL = "wallet operations are not available in this tenant's billing mode ({mode})"

    def setUp(self):
        self.http_client = Client()
        self.postures = {}
        for mode in ("external", "postpaid"):
            tenant = Tenant.objects.create(
                name=mode, products=["metering", "billing"], billing_mode=mode)
            _key, raw = TenantApiKey.create_key(tenant, label="t")
            customer = Customer.objects.create(tenant=tenant, external_id=f"c_{mode}")
            self.postures[mode] = (tenant, raw, customer)

    def _call(self, raw, method, path, body=None):
        kwargs = {"HTTP_AUTHORIZATION": f"Bearer {raw}"}
        if body is not None:
            kwargs.update(data=json.dumps(body), content_type="application/json")
        return getattr(self.http_client, method)(path, **kwargs)

    def _refused(self, response, mode):
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response["Content-Type"], "application/problem+json")
        body = response.json()
        self.assertEqual(body["code"], "feature_not_enabled")
        self.assertEqual(body["detail"], self.DETAIL.format(mode=mode))
        self.assertNotIn("product", body["detail"])

    def _nothing_written(self, tenant, customer):
        from apps.billing.topups.models import TopUpAttempt
        from apps.billing.wallets.models import (
            CreditGrant, WalletReservation, WalletTransaction)
        from apps.platform.events.models import OutboxEvent
        self.assertFalse(Wallet.all_objects.filter(customer=customer).exists())
        self.assertFalse(WalletTransaction.objects.filter(wallet__customer=customer).exists())
        self.assertFalse(CreditGrant.objects.filter(wallet__customer=customer).exists())
        self.assertFalse(WalletReservation.objects.filter(tenant=tenant).exists())
        self.assertFalse(TopUpAttempt.objects.filter(customer=customer).exists())
        self.assertFalse(AutoTopUpConfig.objects.filter(customer=customer).exists())
        self.assertFalse(OutboxEvent.objects.filter(tenant_id=tenant.id).exists())

    def _wallet_mutations(self, customer):
        cid = customer.id
        return {
            "POST /billing/credit": ("post", "/api/v1/billing/credit", {
                "customer_id": str(customer.id), "amount_micros": 1_000_000,
                "source": "manual", "reference": "r", "idempotency_key": "k_credit"}),
            "POST /billing/debit": ("post", "/api/v1/billing/debit", {
                "customer_id": str(customer.id), "amount_micros": 1_000_000,
                "reference": "r", "idempotency_key": "k_debit", "allow_negative": True}),
            "POST …/withdraw": ("post", f"/api/v1/billing/customers/{cid}/withdraw", {
                "amount_micros": 1_000_000, "idempotency_key": "k_withdraw"}),
            "POST …/refund": ("post", f"/api/v1/billing/customers/{cid}/refund", {
                "usage_event_id": str(uuid.uuid4()), "idempotency_key": "k_refund"}),
            "POST …/grants": ("post", f"/api/v1/billing/customers/{cid}/grants", {
                "kind": "promo", "amount_micros": 1_000_000, "expires_in_days": 30,
                "idempotency_key": "k_grant"}),
            "POST …/grants/{id}/void": (
                "post", f"/api/v1/billing/customers/{cid}/grants/{uuid.uuid4()}/void", {}),
            "POST …/top-up": ("post", f"/api/v1/billing/customers/{cid}/top-up", {
                "amount_micros": 1_000_000, "success_url": "https://x.test/s",
                "cancel_url": "https://x.test/c", "idempotency_key": "k_topup"}),
            "PUT …/auto-top-up": ("put", f"/api/v1/billing/customers/{cid}/auto-top-up", {
                "is_enabled": True, "trigger_threshold_micros": 1_000_000,
                "top_up_amount_micros": 5_000_000}),
        }

    def test_every_wallet_mutating_route_refuses_by_name_and_writes_nothing(self):
        for mode, (tenant, raw, customer) in self.postures.items():
            for route, (method, path, body) in self._wallet_mutations(customer).items():
                with self.subTest(mode=mode, route=route):
                    self._refused(self._call(raw, method, path, body), mode)
                    self._nothing_written(tenant, customer)

    def test_the_non_wallet_billing_surface_stays(self):
        for mode, (tenant, raw, customer) in self.postures.items():
            with self.subTest(mode=mode):
                pool = self._call(
                    raw, "put", f"/api/v1/billing/customers/{customer.id}/customer-spend-pool",
                    {"cap_micros": 5_000_000})
                self.assertEqual(pool.status_code, 200, pool.content)
                self.assertEqual(pool.json()["cap_micros"], 5_000_000)
                afford = self._call(
                    raw, "get", f"/api/v1/billing/customers/{customer.id}/affordability")
                self.assertEqual(afford.status_code, 200, afford.content)
                self.assertTrue(afford.json()["allowed"])
                self._nothing_written(tenant, customer)
        _tenant, raw, _customer = self.postures["postpaid"]
        config = self._call(raw, "put", "/api/v1/billing/postpaid-config",
                            {"consolidate_with_subscription": False})
        self.assertEqual(config.status_code, 200, config.content)

    def test_every_wallet_only_read_refuses_by_name(self):
        """R10 Stage C5 (F-12): the wallet-only READS — balance, transactions,
        grants — are refused by the same door as the writes where no wallet
        is: `feature_not_enabled` with the one detail naming the mode, and
        nothing written (no zero-balance wallet invented to be read)."""
        for mode, (tenant, raw, customer) in self.postures.items():
            cid = customer.id
            for route, path in {
                "GET …/balance": f"/api/v1/billing/customers/{cid}/balance",
                "GET …/transactions": f"/api/v1/billing/customers/{cid}/transactions",
                "GET …/grants": f"/api/v1/billing/customers/{cid}/grants",
            }.items():
                with self.subTest(mode=mode, route=route):
                    self._refused(self._call(raw, "get", path), mode)
                    self._nothing_written(tenant, customer)

    def test_the_affordability_balance_figures_are_null_off_the_wallet_lane(self):
        """R10 Stage C5 (F-12): the affordability answer stays (it is not a
        wallet read — it asks whether work may start), but off the wallet
        lane its balance figures are `null`, never a `0` that would report a
        wallet the mode never held."""
        for mode, (tenant, raw, customer) in self.postures.items():
            with self.subTest(mode=mode):
                afford = self._call(
                    raw, "get", f"/api/v1/billing/customers/{customer.id}/affordability")
                self.assertEqual(afford.status_code, 200, afford.content)
                answer = afford.json()
                self.assertTrue(answer["allowed"])
                self.assertIsNone(answer["balance_micros"])
                self.assertIsNone(answer["available_micros"])
                self.assertIsNone(answer["min_balance_micros"])
                self.assertIsNone(answer["soft_min_balance_micros"])
                self._nothing_written(tenant, customer)


class TheCreditAndDebitNameThePlatformUuidTest(RailActivated, TestCase):
    """R10 Stage C5 (F-13, RULED Q13): `POST /billing/credit` and
    `POST /billing/debit` name the customer by its PLATFORM UUID — the same
    identifier every other billing route takes in its path — never by the
    tenant's external id. The body channel is typed `UUID`, so an external id
    is a validation error before any lookup; a well-formed UUID that names
    no customer of the tenant is `not_found`; and there is no server-side
    fallback from the external id, so an external id that happens to be a
    UUID string is not a second way to name the row.
    """

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="UUID Tenant", products=["metering", "billing"],
            billing_mode="prepaid")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="acme-customer-7")
        Wallet.objects.create(customer=self.customer, balance_micros=5_000_000)

    def _post(self, route, body):
        return self.http_client.post(
            f"/api/v1/billing/{route}", data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _credit_body(self, customer_id, key):
        return {"customer_id": customer_id, "amount_micros": 1_000_000,
                "source": "manual", "reference": "r", "idempotency_key": key}

    def _debit_body(self, customer_id, key):
        return {"customer_id": customer_id, "amount_micros": 1_000_000,
                "reference": "r", "idempotency_key": key}

    def test_the_platform_uuid_is_accepted_and_audited_as_the_uuid(self):
        from apps.platform.audit.models import AuditRecord
        uuid_str = str(self.customer.id)
        credited = self._post("credit", self._credit_body(uuid_str, "k_c"))
        self.assertEqual(credited.status_code, 200, credited.content)
        debited = self._post("debit", self._debit_body(uuid_str, "k_d"))
        self.assertEqual(debited.status_code, 200, debited.content)
        self.assertEqual(Wallet.objects.get(customer=self.customer).balance_micros,
                         5_000_000)
        for action in ("wallet.credited", "wallet.debited"):
            with self.subTest(action=action):
                rec = AuditRecord.objects.get(action=action)
                self.assertEqual(rec.metadata["customer_id"], uuid_str)
                self.assertEqual(rec.resource_id, uuid_str)

    def test_the_external_id_is_a_validation_error_and_an_unknown_uuid_is_not_found(self):
        from apps.billing.wallets.models import WalletTransaction
        for route, body_of in (("credit", self._credit_body), ("debit", self._debit_body)):
            with self.subTest(route=route, named_by="external_id"):
                r = self._post(route, body_of(self.customer.external_id, f"k_ext_{route}"))
                self.assertEqual(r.status_code, 422, r.content)
                self.assertEqual(r["Content-Type"], "application/problem+json")
                self.assertEqual(r.json()["code"], "validation_error")
            with self.subTest(route=route, named_by="unknown_uuid"):
                r = self._post(route, body_of(str(uuid.uuid4()), f"k_unk_{route}"))
                self.assertEqual(r.status_code, 404, r.content)
                self.assertEqual(r.json()["code"], "not_found")
        self.assertEqual(Wallet.objects.get(customer=self.customer).balance_micros,
                         5_000_000)
        self.assertFalse(WalletTransaction.objects.filter(
            wallet__customer=self.customer).exists())

    def test_no_fallback_finds_a_customer_by_an_external_id_shaped_like_a_uuid(self):
        looks_like_a_uuid = str(uuid.uuid4())
        other = Customer.objects.create(tenant=self.tenant, external_id=looks_like_a_uuid)
        self.assertNotEqual(str(other.id), looks_like_a_uuid)
        Wallet.objects.create(customer=other, balance_micros=5_000_000)
        for route, body_of in (("credit", self._credit_body), ("debit", self._debit_body)):
            with self.subTest(route=route):
                r = self._post(route, body_of(looks_like_a_uuid, f"k_shape_{route}"))
                self.assertEqual(r.status_code, 404, r.content)
                self.assertEqual(r.json()["code"], "not_found")
        self.assertEqual(Wallet.objects.get(customer=other).balance_micros, 5_000_000)


class ARefundAnswersOneDurableIdTest(RailActivated, TestCase):
    """R10 Stage C5 (F-14, RULED Q14): `POST …/refund` answers `refund_id` =
    the refund WalletTransaction's own id on the first call AND on every
    replay of the same idempotency key (it used to answer the usage event id
    on a replay), and a key already spent by a NON-refund transaction is a
    `conflict`, never replayed as if it were a refund.
    """

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Refund Tenant", products=["metering", "billing"],
            billing_mode="prepaid")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="ref_1")
        self.wallet = Wallet.objects.create(customer=self.customer, balance_micros=5_000_000)
        self.event = a_posting(
            tenant=self.tenant, customer=self.customer, idempotency_key="idem_refund_1",
            provider_cost_micros=1_000_000, billed_cost_micros=1_000_000)

    def _post(self, path, body):
        return self.http_client.post(
            path, data=json.dumps(body), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _refund(self, key):
        return self._post(
            f"/api/v1/billing/customers/{self.customer.id}/refund",
            {"usage_event_id": str(self.event.id), "idempotency_key": key})

    def test_a_refund_replay_answers_the_same_refund_id(self):
        from apps.billing.wallets.models import WalletTransaction
        first = self._refund("rk_same")
        self.assertEqual(first.status_code, 200, first.content)
        again = self._refund("rk_same")
        self.assertEqual(again.status_code, 200, again.content)
        refund_row = WalletTransaction.objects.get(
            wallet=self.wallet, transaction_type="refund")
        self.assertEqual(first.json()["refund_id"], str(refund_row.id))
        self.assertEqual(again.json()["refund_id"], str(refund_row.id))
        self.assertNotEqual(again.json()["refund_id"], str(self.event.id))
        self.assertEqual(again.json()["balance_micros"], first.json()["balance_micros"])
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 6_000_000)  # moved once

    def test_a_refund_key_belonging_to_a_non_refund_transaction_is_a_conflict(self):
        from apps.billing.wallets.models import WalletTransaction
        credited = self._post("/api/v1/billing/credit", {
            "customer_id": str(self.customer.id), "amount_micros": 1_000_000,
            "source": "manual", "reference": "r", "idempotency_key": "K_shared"})
        self.assertEqual(credited.status_code, 200, credited.content)
        r = self._refund("K_shared")
        self.assertEqual(r.status_code, 409, r.content)
        self.assertEqual(r["Content-Type"], "application/problem+json")
        body = r.json()
        self.assertEqual(body["code"], "conflict")
        self.assertIn("non-refund", body["detail"])
        self.assertFalse(WalletTransaction.objects.filter(
            wallet=self.wallet, transaction_type="refund").exists())
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 6_000_000)  # the credit only


class TheUsageInvoiceRoutesShareOneShapeTest(RailActivated, TestCase):
    """R10 Stage C5 (F-15, RULED Q15): the three usage-invoice routes project
    the same durable row the same way. Every row carries one shared base;
    the two TENANT routes add — and only add — the operator's push
    bookkeeping (`push_attempts`, `last_attempt_error`); the end customer's
    `/me` route never carries it. `payment_status` is `null` for a row not
    yet collectible and otherwise one of open|paid|void|uncollectible.
    """

    BASE = frozenset({
        "id", "customer_id", "external_id", "period_start", "period_end",
        "currency", "total_billed_micros", "status", "skip_reason",
        "stripe_invoice_id", "pushed_at", "payment_status", "paid_at",
        "payment_failed_at", "hosted_invoice_url", "invoice_pdf", "created_at"})
    OPERATOR_ONLY = frozenset({"push_attempts", "last_attempt_error"})

    def setUp(self):
        from datetime import date
        from apps.billing.invoicing.models import CustomerUsageInvoice
        from core.widget_auth import create_widget_token
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Shape Tenant", products=["metering", "billing"],
            billing_mode="postpaid")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="shape_1")
        self.token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id))
        self.pushed = CustomerUsageInvoice.objects.create(
            tenant=self.tenant, customer=self.customer,
            period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
            total_billed_micros=12_340_000, status="pushed",
            payment_status="open", stripe_invoice_id="in_1", push_attempts=1)
        self.not_yet_collectible = CustomerUsageInvoice.objects.create(
            tenant=self.tenant, customer=self.customer,
            period_start=date(2026, 6, 1), period_end=date(2026, 6, 30),
            total_billed_micros=5_000_000, status="pending",
            payment_status=None)

    def _rows(self, path, token):
        response = self.http_client.get(path, HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()["data"]
        self.assertEqual(len(rows), 2, rows)
        return {row["id"]: row for row in rows}

    def test_the_three_usage_invoice_routes_share_one_base_shape(self):
        from datetime import date
        by_route = {
            "GET …/customers/{id}/usage-invoices": self._rows(
                f"/api/v1/billing/customers/{self.customer.id}/usage-invoices",
                self.raw_key),
            "GET …/tenant/usage-invoices": self._rows(
                "/api/v1/billing/tenant/usage-invoices", self.raw_key),
            "GET /me/usage-invoices": self._rows(
                "/api/v1/me/usage-invoices", self.token),
        }
        for route, rows in by_route.items():
            expected = (self.BASE if route.startswith("GET /me")
                        else self.BASE | self.OPERATOR_ONLY)
            for row_id, row in rows.items():
                with self.subTest(route=route, row=row_id):
                    self.assertEqual(set(row), expected)
                    self.assertEqual(row["customer_id"], str(self.customer.id))
                    self.assertEqual(row["external_id"], "shape_1")
                    self.assertEqual(row["currency"], "usd")
                    date.fromisoformat(row["period_start"])  # an ISO date
                    date.fromisoformat(row["period_end"])
            with self.subTest(route=route, row="pushed"):
                row = rows[str(self.pushed.id)]
                self.assertEqual(row["payment_status"], "open")
                self.assertEqual(row["status"], "pushed")
                self.assertEqual(row["stripe_invoice_id"], "in_1")
                self.assertEqual(row["period_start"], "2026-05-01")
                self.assertEqual(row["period_end"], "2026-05-31")
            with self.subTest(route=route, row="not_yet_collectible"):
                row = rows[str(self.not_yet_collectible.id)]
                self.assertIsNone(row["payment_status"])
                self.assertEqual(row["status"], "pending")
                self.assertEqual(row["stripe_invoice_id"], "")
        # The same row's `created_at` reads the same on all three routes.
        for row_id in (str(self.pushed.id), str(self.not_yet_collectible.id)):
            with self.subTest(row=row_id, field="created_at"):
                stamps = {route: rows[row_id]["created_at"] for route, rows in by_route.items()}
                self.assertEqual(len(set(stamps.values())), 1, stamps)
                self.assertIsNotNone(next(iter(stamps.values())))
        # The tenant rows carry the push bookkeeping the /me rows never do.
        tenant_rows = by_route["GET …/tenant/usage-invoices"]
        self.assertEqual(tenant_rows[str(self.pushed.id)]["push_attempts"], 1)
        self.assertEqual(tenant_rows[str(self.pushed.id)]["last_attempt_error"], "")
