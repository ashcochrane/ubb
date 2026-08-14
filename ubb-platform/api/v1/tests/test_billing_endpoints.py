import json
from unittest.mock import patch

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.platform.work.models import Task
from apps.billing.topups.models import AutoTopUpConfig
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

    # The billing-mount duplicates of tenant billing-periods/invoices were
    # removed in the Stage-5 final sweep (#86); the canonical routes on the
    # tenant mount (which do not gate on the billing product) are covered by
    # test_tenant_endpoints.py.


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
                "customer_id": "cust_debit_1",
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
                "customer_id": "cust_debit_1",
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
                "customer_id": "cust_debit_1",
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
                "customer_id": "cust_debit_1",
                "amount_micros": 500_000,
                "reference": "ref_3",
                "idempotency_key": "idem_d_ref_3",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    # --- floor guard (Phase 1): debit respects the overdraft floor by default ---

    def _debit(self, external_id, amount, key, allow_negative=None):
        body = {"customer_id": external_id, "amount_micros": amount,
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
        resp = self._debit("od_1", 2_000_000, "od_k1")
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
        resp = self._debit("od_2", 2_000_000, "od_k2", allow_negative=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Wallet.objects.get(customer=c).balance_micros, -1_000_000)

    def test_debit_within_overdraft_cushion_allowed(self):
        from apps.billing.wallets.models import CustomerBillingProfile
        c = Customer.objects.create(tenant=self.tenant, external_id="od_3")
        Wallet.objects.create(customer=c, balance_micros=1_000_000)
        CustomerBillingProfile.objects.create(customer=c, min_balance_micros=5_000_000)
        resp = self._debit("od_3", 3_000_000, "od_k3")  # -> -2M, floor -5M: allowed
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Wallet.objects.get(customer=c).balance_micros, -2_000_000)

    def test_debit_postpaid_skips_floor(self):
        self.tenant.billing_mode = "postpaid"
        self.tenant.save()
        c = Customer.objects.create(tenant=self.tenant, external_id="od_4")
        Wallet.objects.create(customer=c, balance_micros=0)
        resp = self._debit("od_4", 1_000_000, "od_k4")  # postpaid: negative is normal
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Wallet.objects.get(customer=c).balance_micros, -1_000_000)

    # --- attribution (Phase 1): reason_code + actor stored on the ledger ---

    def test_debit_records_reason_code_and_actor(self):
        from apps.billing.wallets.models import WalletTransaction
        resp = self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({"customer_id": "cust_debit_1", "amount_micros": 1_000_000,
                             "reference": "adj", "idempotency_key": "attr_k1",
                             "reason_code": "correction", "actor": "ops@acme.co"}),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(resp.status_code, 200)
        txn = WalletTransaction.objects.get(id=resp.json()["transaction_id"])
        self.assertEqual(txn.reason_code, "correction")
        self.assertEqual(txn.actor, "ops@acme.co")

    def test_debit_rejects_unknown_reason_code(self):
        resp = self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({"customer_id": "cust_debit_1", "amount_micros": 1_000_000,
                             "reference": "adj", "idempotency_key": "attr_k2",
                             "reason_code": "bogus"}),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(resp.status_code, 422)


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
                "customer_id": "cust_credit_1",
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
                "customer_id": "cust_credit_1",
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
                "customer_id": "cust_credit_1",
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
                "customer_id": "cust_credit_1",
                "amount_micros": 500_000,
                "source": "test",
                "reference": "ref_3",
                "idempotency_key": "idem_c_ref_3",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_credit_records_reason_code_and_actor(self):
        from apps.billing.wallets.models import WalletTransaction
        response = self.http_client.post(
            "/api/v1/billing/credit",
            data=json.dumps({"customer_id": "cust_credit_1", "amount_micros": 1_000_000,
                             "source": "manual", "reference": "adj",
                             "idempotency_key": "attr_c1",
                             "reason_code": "goodwill", "actor": "ops@acme.co"}),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(response.status_code, 200)
        txn = WalletTransaction.objects.get(id=response.json()["transaction_id"])
        self.assertEqual(txn.reason_code, "goodwill")
        self.assertEqual(txn.actor, "ops@acme.co")


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
                "customer_id": "no_wallet_credit",
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
                "idempotency_key": "idem_ref_lock",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        from apps.billing.wallets.models import WalletTransaction
        txn = WalletTransaction.objects.get(wallet__customer=customer)
        self.assertEqual(txn.transaction_type, "DEBIT")
        self.assertEqual(txn.balance_after_micros, 4_000_000)

    def test_debit_requires_idempotency_key(self):
        Customer.objects.create(tenant=self.tenant, external_id="need_key_d")
        resp = self.http_client.post(
            "/api/v1/billing/debit",
            data=json.dumps({"customer_id": "need_key_d", "amount_micros": 1_000_000,
                             "reference": "ref_nokey"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(resp.status_code, 422)

    def test_credit_requires_idempotency_key(self):
        Customer.objects.create(tenant=self.tenant, external_id="need_key_c")
        resp = self.http_client.post(
            "/api/v1/billing/credit",
            data=json.dumps({"customer_id": "need_key_c", "amount_micros": 1_000_000,
                             "source": "x", "reference": "ref_nokey"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(resp.status_code, 422)


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


class PreCheckTaskTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Task Tenant",
            products=["metering", "billing"],
        )
        BillingTenantConfig.objects.create(tenant=self.tenant)
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_task_1"
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

    def test_pre_check_start_task_returns_task_id(self):
        # Uncapped start (no provider_cost_limit_micros anywhere) — the
        # coverage gate only fires for a RESOLVED limit, so no coverage
        # setup is needed here.
        resp = self._pre_check(start_task=True)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["allowed"])
        self.assertIsNotNone(body["task_id"])
        self.assertIsNone(body["provider_cost_limit_micros"])

        # Task exists in DB
        task = Task.objects.get(id=body["task_id"])
        self.assertEqual(task.status, "active")
        self.assertEqual(task.balance_snapshot_micros, 20_000_000)
        self.assertIsNone(task.provider_cost_limit_micros)

    def test_pre_check_capped_start_snapshots_limit(self):
        # This tenant has declared no cost rates at all, and a limited start
        # is admitted anyway (#321): the coverage gate that refused one is
        # gone, with nothing in its place. What used to justify it — a COGS
        # ceiling racing a total that silently counted uncovered events as 0 —
        # stopped being true in #320, which records an uncosted event with its
        # cost unresolved instead of counting it as nothing.
        resp = self._pre_check(start_task=True, provider_cost_limit_micros=10_000_000)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["allowed"])
        self.assertEqual(body["provider_cost_limit_micros"], 10_000_000)
        task = Task.objects.get(id=body["task_id"])
        self.assertEqual(task.provider_cost_limit_micros, 10_000_000)

    def test_pre_check_start_task_denied_no_task_created(self):
        self.wallet.balance_micros = -6_000_000
        self.wallet.save()

        resp = self._pre_check(start_task=True)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["allowed"])
        self.assertIsNone(body["task_id"])
        self.assertEqual(Task.objects.count(), 0)

    def test_pre_check_without_start_task_returns_null_task(self):
        resp = self._pre_check()
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["allowed"])
        self.assertIsNone(body["task_id"])


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


class TopUpAttemptBillingOwnerPinTest(TestCase):
    """Task 7 — create_top_up must pin TopUpAttempt.billing_owner_id at
    creation, across all three topologies. `customer` on the row always
    stays the SEAT (who initiated); this test asserts what actually gets
    pinned into billing_owner_id, the value both credit_top_up call sites
    key on later."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="No Stripe Pin Tenant", products=["metering", "billing"],
            stripe_connected_account_id="",
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


class PooledSeatBillingSurfaceTest(TestCase):
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
            name="Pooled Tenant", products=["metering", "billing"]
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
            data=json.dumps({"customer_id": "seat_pooled", "amount_micros": 2_000_000,
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
            data=json.dumps({"customer_id": "seat_alloc", "amount_micros": 1_000_000,
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
            data=json.dumps({"customer_id": "seat_pooled", "amount_micros": 1_000_000,
                             "reference": "r1", "idempotency_key": "dk_audit"}),
            content_type="application/json", **self._auth())
        rec = AuditRecord.objects.get(action="wallet.debited")
        self.assertEqual(rec.resource_id, str(self.pooled_seat.id))
        self.assertEqual(rec.metadata["customer_id"], "seat_pooled")
        self.assertEqual(rec.metadata["owner_id"], str(self.pooled_biz.id))

    # ---------- credit ----------

    def test_credit_pooled_seat_moves_business_wallet_no_second_wallet(self):
        r = self.http_client.post(
            "/api/v1/billing/credit",
            data=json.dumps({"customer_id": "seat_pooled", "amount_micros": 3_000_000,
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
            data=json.dumps({"customer_id": "seat_alloc", "amount_micros": 2_000_000,
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
            data=json.dumps({"customer_id": "seat_pooled", "amount_micros": 1_000_000,
                             "source": "manual", "reference": "r1",
                             "idempotency_key": "ck_audit"}),
            content_type="application/json", **self._auth())
        rec = AuditRecord.objects.get(action="wallet.credited")
        self.assertEqual(rec.resource_id, str(self.pooled_seat.id))
        self.assertEqual(rec.metadata["customer_id"], "seat_pooled")
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

    def _usage_event(self, customer, amount=1_000_000, request_id="r1"):
        from apps.metering.usage.models import Posting
        return Posting.objects.create(
            tenant=self.tenant, customer=customer, request_id=request_id,
            idempotency_key=f"idem_{request_id}",
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
        event = self._usage_event(self.alloc_seat, amount=1_000_000, request_id="r2")
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
        event = self._usage_event(self.individual, amount=1_000_000, request_id="r3")
        r = self.http_client.post(
            f"/api/v1/billing/customers/{self.individual.id}/refund",
            data=json.dumps({"usage_event_id": str(event.id),
                             "idempotency_key": "rk_ind"}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            Wallet.objects.get(customer=self.individual).balance_micros, 6_000_000)

    def test_refund_audit_keeps_seat_as_subject_and_records_owner(self):
        from apps.platform.audit.models import AuditRecord
        Wallet.objects.create(customer=self.pooled_biz, balance_micros=5_000_000)
        event = self._usage_event(self.pooled_seat, amount=1_000_000, request_id="r4")
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
