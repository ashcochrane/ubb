"""F4.3 — credit grant API: create/list/void, withdrawal promo exclusion,
/me grants + balance grant fields, lot-aware usage refunds."""
import json
import uuid
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from apps.billing.handlers import handle_usage_recorded_billing
from apps.billing.wallets.models import (
    CreditGrant, GrantAllocation, Wallet, WalletTransaction,
)
from apps.metering.usage.models import UsageEvent
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
            "amount_micros": 8_000_000, "reference": "evt_x",
            "idempotency_key": "idem_evt_x"})
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


class RefundLotAwareTest(TestCase):
    """Fix 2 — /refund re-funds the grant lots that funded the usage, closing
    the promo cash-out hole (promo -> spend -> refund -> withdraw)."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="RF", products=["metering", "billing"], billing_mode="prepaid")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_rf_1")
        self.wallet = Wallet.objects.create(customer=self.customer, balance_micros=0)

    def _post(self, path, body):
        return self.http_client.post(
            path, data=json.dumps(body), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _grant(self, kind, amount, key, **extra):
        body = {"kind": kind, "amount_micros": amount, "idempotency_key": key}
        body.update(extra)
        resp = self._post(
            f"/api/v1/billing/customers/{self.customer.id}/grants", body)
        assert resp.status_code == 200, resp.content
        return resp.json()["id"]

    def _spend(self, cost):
        """Record a real UsageEvent + drive the live drawdown handler."""
        ev = UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id=f"req-{uuid.uuid4()}",
            idempotency_key=f"uek-{uuid.uuid4()}",
            billed_cost_micros=cost)
        handle_usage_recorded_billing(str(uuid.uuid4()), {
            "tenant_id": str(self.tenant.id),
            "customer_id": str(self.customer.id),
            "event_id": str(ev.id),
            "billing_owner_id": str(self.customer.id),
            "cost_micros": cost})
        return ev

    def _refund(self, ev, key):
        return self._post(
            f"/api/v1/billing/customers/{self.customer.id}/refund",
            {"usage_event_id": str(ev.id), "idempotency_key": key})

    def _withdraw(self, amount, key):
        return self._post(
            f"/api/v1/billing/customers/{self.customer.id}/withdraw",
            {"amount_micros": amount, "idempotency_key": key})

    def test_promo_funded_refund_restores_lot_not_cash(self):
        """promo 100 -> spend 100 -> refund: the promo lot comes back and the
        money is still NOT withdrawable (the old behavior turned it into
        withdrawable base cash)."""
        grant_id = self._grant("promo", 100_000_000, "rf_promo")
        ev = self._spend(100_000_000)
        grant = CreditGrant.objects.get(pk=grant_id)
        self.assertEqual(grant.status, "depleted")

        resp = self._refund(ev, "rf1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["balance_micros"], 100_000_000)

        grant.refresh_from_db()
        self.assertEqual(grant.status, "active")  # depleted -> active again
        self.assertEqual(grant.remaining_micros, 100_000_000)
        alloc = GrantAllocation.objects.get(grant=grant, allocation_type="usage")
        self.assertEqual(alloc.refunded_micros, 100_000_000)
        # The cash-out hole is closed: nothing withdrawable.
        resp = self._withdraw(100_000_000, "wd_rf1")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Insufficient", resp.json()["error"])

    def test_expired_lot_share_lands_as_base(self):
        """The lot expired between spend and refund: its remainder was already
        destroyed by the expiry debit, so the refund share lands as base."""
        grant_id = self._grant("promo", 100_000_000, "rf_exp",
                               expires_in_days=10)
        ev = self._spend(60_000_000)  # remaining 40, balance 40
        CreditGrant.objects.filter(pk=grant_id).update(
            expires_at=timezone.now() - timedelta(seconds=1))

        resp = self._refund(ev, "rf2")  # endpoint's lazy expire_due fires first
        self.assertEqual(resp.status_code, 200)

        grant = CreditGrant.objects.get(pk=grant_id)
        self.assertEqual(grant.status, "expired")
        self.assertEqual(grant.remaining_micros, 0)  # NOT re-funded
        self.assertEqual(grant.expired_micros, 40_000_000)
        alloc = GrantAllocation.objects.get(grant=grant, allocation_type="usage")
        self.assertEqual(alloc.refunded_micros, 0)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 60_000_000)  # all base
        self.assertEqual(self._withdraw(60_000_000, "wd_rf2").status_code, 200)

    def test_mixed_lot_and_base_refund_splits(self):
        """base 50 + promo 30, spend 70 (promo 30 + base 40): the refund puts
        30 back into the promo lot and 40 back as base."""
        Wallet.objects.filter(pk=self.wallet.pk).update(
            balance_micros=50_000_000)  # base 50
        grant_id = self._grant("promo", 30_000_000, "rf_mix")
        ev = self._spend(70_000_000)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 10_000_000)

        resp = self._refund(ev, "rf3")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["balance_micros"], 80_000_000)

        grant = CreditGrant.objects.get(pk=grant_id)
        self.assertEqual(grant.remaining_micros, 30_000_000)
        self.assertEqual(grant.status, "active")
        alloc = GrantAllocation.objects.get(grant=grant, allocation_type="usage")
        self.assertEqual(alloc.refunded_micros, 30_000_000)
        # Withdrawable = base 50 only.
        self.assertEqual(self._withdraw(60_000_000, "wd_rf3a").status_code, 400)
        self.assertEqual(self._withdraw(50_000_000, "wd_rf3b").status_code, 200)

    def test_double_refund_replay_and_new_key_capped(self):
        """Replay (same idempotency key) is a pure no-op; a SECOND refund of
        the same event under a new key credits cash again but the lot re-fund
        is capped by refunded_micros — the lot is never double-restored."""
        grant_id = self._grant("promo", 50_000_000, "rf_dbl")
        ev = self._spend(50_000_000)

        r1 = self._refund(ev, "rf4")
        self.assertEqual(r1.status_code, 200)
        r2 = self._refund(ev, "rf4")  # replay
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["balance_micros"], 50_000_000)
        self.assertEqual(WalletTransaction.objects.filter(
            wallet=self.wallet, transaction_type="REFUND").count(), 1)
        grant = CreditGrant.objects.get(pk=grant_id)
        self.assertEqual(grant.remaining_micros, 50_000_000)
        alloc = GrantAllocation.objects.get(grant=grant, allocation_type="usage")
        self.assertEqual(alloc.refunded_micros, 50_000_000)

        # Different key: the cash credit happens (caller's policy call), but
        # the lot stays capped at granted and refunded_micros at amount.
        r3 = self._refund(ev, "rf5")
        self.assertEqual(r3.status_code, 200)
        self.assertEqual(r3.json()["balance_micros"], 100_000_000)
        grant.refresh_from_db()
        alloc.refresh_from_db()
        self.assertEqual(grant.remaining_micros, 50_000_000)  # NOT 100
        self.assertEqual(alloc.refunded_micros, 50_000_000)   # capped
        # G2 stays exact: 50 == 50 + (50 - 50) + 0 + 0.
        self.assertEqual(grant.granted_micros, 50_000_000)

    def test_reconcile_silent_after_refund(self):
        """The conservation equation holds after a lot-aware refund."""
        import logging as _logging
        from apps.billing.wallets.tasks import reconcile_wallet_balances
        self._grant("promo", 40_000_000, "rf_rec")
        ev = self._spend(25_000_000)
        self.assertEqual(self._refund(ev, "rf6").status_code, 200)

        records = []

        class Capture(_logging.Handler):
            def emit(self, record):
                records.append(record)

        logger = _logging.getLogger("apps.billing.wallets.tasks")
        handler = Capture()
        logger.addHandler(handler)
        try:
            reconcile_wallet_balances()
        finally:
            logger.removeHandler(handler)
        errors = [r.getMessage() for r in records
                  if r.levelno >= _logging.ERROR]
        self.assertEqual(errors, [])


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
