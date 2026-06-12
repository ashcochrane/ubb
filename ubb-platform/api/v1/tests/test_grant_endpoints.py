"""F4.3 — credit grant API: create/list/void, withdrawal promo exclusion,
/me grants + balance grant fields."""
import json
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from apps.billing.wallets.models import (
    CreditGrant, GrantAllocation, Wallet, WalletTransaction,
)
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.widget_auth import create_widget_token


class GrantEndpointsTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Grants", products=["metering", "billing"], billing_mode="prepaid")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_grants_1")
        self.wallet = Wallet.objects.create(customer=self.customer, balance_micros=0)

    def _post(self, path, body):
        return self.http_client.post(
            path, data=json.dumps(body), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _create_grant(self, **overrides):
        body = {"kind": "promo", "amount_micros": 10_000_000,
                "expires_in_days": 30, "idempotency_key": "k1"}
        body.update(overrides)
        return self._post(f"/api/v1/billing/customers/{self.customer.id}/grants", body)

    def test_create_grant_credits_wallet_and_creates_lot(self):
        resp = self._create_grant()
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["kind"], "promo")
        self.assertEqual(body["granted_micros"], 10_000_000)
        self.assertEqual(body["remaining_micros"], 10_000_000)
        self.assertEqual(body["status"], "active")
        self.assertEqual(body["source"], "api")
        self.assertEqual(body["balance_micros"], 10_000_000)
        self.assertIsNotNone(body["expires_at"])
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 10_000_000)
        txn = WalletTransaction.objects.get(
            wallet=self.wallet, idempotency_key="grant:k1")
        self.assertEqual(txn.transaction_type, "GRANT")
        self.assertEqual(txn.amount_micros, 10_000_000)

    def test_create_grant_idempotent_replay(self):
        r1 = self._create_grant()
        r2 = self._create_grant()  # same idempotency_key
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json()["id"], r2.json()["id"])
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 10_000_000)
        self.assertEqual(CreditGrant.objects.count(), 1)
        self.assertEqual(WalletTransaction.objects.filter(
            wallet=self.wallet, transaction_type="GRANT").count(), 1)

    def test_create_grant_rejects_both_expiry_forms(self):
        resp = self._create_grant(
            expires_at=(timezone.now() + timedelta(days=5)).isoformat(),
            expires_in_days=5)
        self.assertEqual(resp.status_code, 400)

    def test_create_grant_rejects_past_expires_at(self):
        resp = self._create_grant(
            expires_at=(timezone.now() - timedelta(days=1)).isoformat(),
            expires_in_days=None)
        self.assertEqual(resp.status_code, 400)

    def test_create_grant_rejects_bad_kind_and_uncented_amount(self):
        self.assertEqual(self._create_grant(kind="bonus").status_code, 422)
        self.assertEqual(self._create_grant(amount_micros=10_000_001).status_code, 422)

    def test_create_grant_requires_idempotency_key(self):
        resp = self._create_grant(idempotency_key="")
        self.assertEqual(resp.status_code, 422)

    def test_list_grants_with_status_filter(self):
        self._create_grant(idempotency_key="ka", kind="promo")
        self._create_grant(idempotency_key="kb", kind="paid")
        resp = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/grants",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["data"]), 2)
        self.assertFalse(body["has_more"])
        resp = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/grants?status=voided",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(len(resp.json()["data"]), 0)

    def test_void_grant_debits_remaining_and_is_idempotent(self):
        grant_id = self._create_grant().json()["id"]
        resp = self._post(
            f"/api/v1/billing/customers/{self.customer.id}/grants/{grant_id}/void", {})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "voided")
        self.assertEqual(body["remaining_micros"], 0)
        self.assertEqual(body["voided_micros"], 10_000_000)
        self.assertEqual(body["balance_micros"], 0)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 0)
        void_txns = WalletTransaction.objects.filter(
            wallet=self.wallet, idempotency_key=f"grant_void:{grant_id}")
        self.assertEqual(void_txns.count(), 1)
        self.assertEqual(void_txns.get().amount_micros, -10_000_000)
        # Second void: no second debit.
        resp = self._post(
            f"/api/v1/billing/customers/{self.customer.id}/grants/{grant_id}/void", {})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "voided")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 0)
        self.assertEqual(WalletTransaction.objects.filter(
            wallet=self.wallet, transaction_type="GRANT_VOID").count(), 1)

    def test_void_clamps_debit_to_balance(self):
        """G3 semantics for void: even with a dented invariant (remaining >
        balance), the void debit never drives the balance below zero."""
        grant_id = self._create_grant(amount_micros=10_000_000).json()["id"]
        # Consume 8 of the lot through /debit, then dent the cached balance.
        self._post("/api/v1/billing/debit", {
            "customer_id": self.customer.external_id,
            "amount_micros": 8_000_000, "reference": "evt_x"})
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 2_000_000)
        grant = CreditGrant.objects.get(pk=grant_id)
        self.assertEqual(grant.remaining_micros, 2_000_000)
        Wallet.objects.filter(pk=self.wallet.pk).update(balance_micros=1_000_000)
        resp = self._post(
            f"/api/v1/billing/customers/{self.customer.id}/grants/{grant_id}/void", {})
        body = resp.json()
        self.assertEqual(body["status"], "voided")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 0)  # clamped at zero
        self.assertEqual(body["voided_micros"], 2_000_000)
        void_txn = WalletTransaction.objects.get(
            wallet=self.wallet, idempotency_key=f"grant_void:{grant_id}")
        self.assertEqual(void_txn.amount_micros, -1_000_000)
        self.assertEqual(void_txn.balance_after_micros, 0)

    def test_balance_includes_grant_fields(self):
        self._create_grant(idempotency_key="kp", kind="promo",
                           amount_micros=6_000_000)
        self._create_grant(idempotency_key="kq", kind="paid",
                           amount_micros=4_000_000, expires_in_days=10)
        resp = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        body = resp.json()
        self.assertEqual(body["balance_micros"], 10_000_000)
        self.assertEqual(body["promo_micros"], 6_000_000)
        self.assertEqual(body["expiring_micros"], 10_000_000)  # both lots expire
        self.assertIsNotNone(body["next_expiry_at"])


class WithdrawExcludesPromoTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="WD", products=["metering", "billing"], billing_mode="prepaid")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_wd_1")
        # Base 40 + promo 60 = balance 100.
        self.wallet = Wallet.objects.create(
            customer=self.customer, balance_micros=40_000_000)
        resp = self.http_client.post(
            f"/api/v1/billing/customers/{self.customer.id}/grants",
            data=json.dumps({"kind": "promo", "amount_micros": 60_000_000,
                             "idempotency_key": "wd_promo"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code == 200

    def _withdraw(self, amount, key):
        return self.http_client.post(
            f"/api/v1/billing/customers/{self.customer.id}/withdraw",
            data=json.dumps({"amount_micros": amount, "idempotency_key": key}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def test_withdraw_more_than_non_promo_rejected(self):
        resp = self._withdraw(50_000_000, "wd1")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Insufficient", resp.json()["error"])
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 100_000_000)

    def test_withdraw_within_non_promo_succeeds_no_promo_allocation(self):
        resp = self._withdraw(40_000_000, "wd2")
        self.assertEqual(resp.status_code, 200)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 60_000_000)
        txn = WalletTransaction.objects.get(
            wallet=self.wallet, idempotency_key="wd2")
        self.assertEqual(GrantAllocation.objects.filter(
            wallet_transaction=txn).count(), 0)
        promo = CreditGrant.objects.get(wallet=self.wallet)
        self.assertEqual(promo.remaining_micros, 60_000_000)  # untouched


class MeGrantsTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="MeG", stripe_connected_account_id="acct_meg",
            products=["metering", "billing"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.wallet = Wallet.objects.create(customer=self.customer, balance_micros=0)
        self.token = create_widget_token(
            self.tenant.widget_secret, str(self.customer.id), str(self.tenant.id))
        resp = self.http_client.post(
            f"/api/v1/billing/customers/{self.customer.id}/grants",
            data=json.dumps({"kind": "promo", "amount_micros": 5_000_000,
                             "expires_in_days": 14, "idempotency_key": "me1"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code == 200

    def test_me_grants_lists_active_lots(self):
        resp = self.http_client.get(
            "/api/v1/me/grants", HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["kind"], "promo")
        self.assertEqual(data[0]["remaining_micros"], 5_000_000)
        self.assertIsNotNone(data[0]["expires_at"])

    def test_me_balance_includes_grant_fields(self):
        resp = self.http_client.get(
            "/api/v1/me/balance", HTTP_AUTHORIZATION=f"Bearer {self.token}")
        body = resp.json()
        self.assertEqual(body["balance_micros"], 5_000_000)
        self.assertEqual(body["promo_micros"], 5_000_000)
        self.assertEqual(body["expiring_micros"], 5_000_000)
        self.assertIsNotNone(body["next_expiry_at"])
