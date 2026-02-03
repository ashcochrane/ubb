import json
import uuid
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client

from apps.tenants.models import Tenant, TenantApiKey
from apps.customers.models import Customer, Wallet, WalletTransaction
from apps.pricing.models import ProviderRate
from apps.usage.models import UsageEvent, Refund


class HealthEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_health_returns_200(self):
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_health_no_auth_required(self):
        # No Authorization header — should still return 200
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)


class ReadyEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_ready_returns_200_when_all_ok(self):
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        with patch("api.v1.endpoints.redis.from_url", return_value=mock_redis):
            response = self.client.get("/api/v1/ready")
            body = response.json()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(body["status"], "ready")
            self.assertEqual(body["checks"]["database"], "ok")
            self.assertEqual(body["checks"]["redis"], "ok")

    def test_ready_no_auth_required(self):
        response = self.client.get("/api/v1/ready")
        self.assertIn(response.status_code, [200, 503])

    def test_ready_returns_503_when_db_fails(self):
        with patch("django.db.connection.ensure_connection", side_effect=Exception("db down")):
            response = self.client.get("/api/v1/ready")
            body = response.json()
            self.assertEqual(body["checks"]["database"], "error")
            self.assertEqual(body["status"], "not_ready")
            self.assertEqual(response.status_code, 503)

    def test_ready_returns_503_when_redis_fails(self):
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("redis down")
        with patch("redis.from_url", return_value=mock_redis):
            response = self.client.get("/api/v1/ready")
            body = response.json()
            self.assertEqual(body["checks"]["redis"], "error")
            self.assertEqual(body["status"], "not_ready")
            self.assertEqual(response.status_code, 503)


class PreCheckEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Test Tenant")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            external_id="cust_001",
        )

    def test_pre_check_active_customer(self):
        response = self.client.post(
            "/api/v1/pre-check",
            data=json.dumps({"customer_id": str(self.customer.id)}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["allowed"])
        self.assertIsNone(body["reason"])

    def test_pre_check_suspended_customer(self):
        self.customer.status = "suspended"
        self.customer.save(update_fields=["status"])
        response = self.client.post(
            "/api/v1/pre-check",
            data=json.dumps({"customer_id": str(self.customer.id)}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["allowed"])
        self.assertEqual(body["reason"], "insufficient_funds")

    def test_unauthenticated_returns_401(self):
        response = self.client.post(
            "/api/v1/pre-check",
            data=json.dumps({"customer_id": str(self.customer.id)}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)


class RecordUsageEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Test Tenant")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            external_id="cust_002",
        )
        # Set wallet balance to $10
        wallet = self.customer.wallet
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])

    def test_record_usage(self):
        response = self.client.post(
            "/api/v1/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_123",
                "idempotency_key": "idem_123",
                "cost_micros": 1_500_000,
                "metadata": {"model": "gpt-4"},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["new_balance_micros"], 8_500_000)
        self.assertFalse(body["suspended"])
        self.assertIn("event_id", body)


class CustomerEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Test Tenant")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def test_create_customer(self):
        response = self.client.post(
            "/api/v1/customers",
            data=json.dumps({
                "external_id": "cust_new",
                "stripe_customer_id": "cus_test123",
                "metadata": {"plan": "pro"},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["external_id"], "cust_new")
        self.assertEqual(body["status"], "active")
        self.assertIn("id", body)

    def test_get_balance(self):
        customer = Customer.objects.create(
            tenant=self.tenant,
            external_id="cust_bal",
        )
        response = self.client.get(
            f"/api/v1/customers/{customer.id}/balance",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["balance_micros"], 0)
        self.assertEqual(body["currency"], "USD")


class WalletTransactionIdempotencyTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Tenant")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )
        self.customer.wallet.balance_micros = 100_000_000
        self.customer.wallet.save()

    def test_idempotency_key_on_wallet_transaction(self):
        txn = WalletTransaction.objects.create(
            wallet=self.customer.wallet,
            transaction_type="WITHDRAWAL",
            amount_micros=-5_000_000,
            balance_after_micros=95_000_000,
            description="Test withdrawal",
            idempotency_key="idem_withdraw_1",
        )
        self.assertEqual(txn.idempotency_key, "idem_withdraw_1")

    def test_duplicate_idempotency_key_raises(self):
        from django.db import IntegrityError, transaction as db_transaction
        WalletTransaction.objects.create(
            wallet=self.customer.wallet,
            transaction_type="WITHDRAWAL",
            amount_micros=-5_000_000,
            balance_after_micros=95_000_000,
            idempotency_key="idem_dup",
        )
        with self.assertRaises(IntegrityError):
            with db_transaction.atomic():
                WalletTransaction.objects.create(
                    wallet=self.customer.wallet,
                    transaction_type="WITHDRAWAL",
                    amount_micros=-5_000_000,
                    balance_after_micros=90_000_000,
                    idempotency_key="idem_dup",
                )


class WithdrawEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Test Tenant")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_w1"
        )
        self.customer.wallet.balance_micros = 50_000_000
        self.customer.wallet.save()

    def test_withdraw_success(self):
        response = self.client.post(
            f"/api/v1/customers/{self.customer.id}/withdraw",
            data=json.dumps({
                "amount_micros": 10_000_000,
                "idempotency_key": "wd_1",
                "description": "Test withdraw",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["balance_micros"], 40_000_000)
        self.assertIn("transaction_id", body)

    def test_withdraw_insufficient_balance(self):
        response = self.client.post(
            f"/api/v1/customers/{self.customer.id}/withdraw",
            data=json.dumps({
                "amount_micros": 999_000_000,
                "idempotency_key": "wd_big",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["error"], "Insufficient balance")

    def test_withdraw_idempotency(self):
        payload = json.dumps({
            "amount_micros": 10_000_000,
            "idempotency_key": "wd_idem",
        })
        r1 = self.client.post(
            f"/api/v1/customers/{self.customer.id}/withdraw",
            data=payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        r2 = self.client.post(
            f"/api/v1/customers/{self.customer.id}/withdraw",
            data=payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        # Balance should only be deducted once
        self.assertEqual(r1.json()["balance_micros"], r2.json()["balance_micros"])


class TransactionsEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Test Tenant")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_tx"
        )
        wallet = self.customer.wallet
        wallet.balance_micros = 100_000_000
        wallet.save()
        # Create some transactions
        for i in range(3):
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type="TOP_UP",
                amount_micros=10_000_000,
                balance_after_micros=100_000_000 + (i + 1) * 10_000_000,
                description=f"Top up {i}",
            )

    def test_list_transactions(self):
        response = self.client.get(
            f"/api/v1/customers/{self.customer.id}/transactions",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["data"]), 3)
        self.assertFalse(body["has_more"])
        self.assertIsNone(body["next_cursor"])


class RefundEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(
            name="Test Tenant", stripe_connected_account_id="acct_test"
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_ref"
        )
        self.customer.wallet.balance_micros = 100_000_000
        self.customer.wallet.save()
        # Create a usage event directly (bypass immutability save override for test)
        from django.utils import timezone
        self.event = UsageEvent(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_refund_1",
            idempotency_key="idem_ref_1",
            cost_micros=5_000_000,
        )
        # Use super().save() to bypass immutability check
        super(UsageEvent, self.event).save()

    def test_refund_succeeds_for_non_invoiced_event(self):
        response = self.client.post(
            f"/api/v1/customers/{self.customer.id}/refund",
            data=json.dumps({
                "usage_event_id": str(self.event.id),
                "reason": "Customer request",
                "idempotency_key": "refund_idem_1",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("refund_id", body)
        self.assertEqual(body["balance_micros"], 105_000_000)

    def test_refund_captures_api_key(self):
        response = self.client.post(
            f"/api/v1/customers/{self.customer.id}/refund",
            data=json.dumps({
                "usage_event_id": str(self.event.id),
                "reason": "Audit test",
                "idempotency_key": "refund_idem_audit",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        refund = Refund.objects.get(usage_event=self.event)
        self.assertEqual(refund.refunded_by_api_key_id, self.key_obj.id)

    def test_double_refund_returns_409(self):
        # First refund
        payload = json.dumps({
            "usage_event_id": str(self.event.id),
            "reason": "First",
            "idempotency_key": "refund_first",
        })
        r1 = self.client.post(
            f"/api/v1/customers/{self.customer.id}/refund",
            data=payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(r1.status_code, 200)

        # Second refund with DIFFERENT idempotency key
        payload2 = json.dumps({
            "usage_event_id": str(self.event.id),
            "reason": "Second",
            "idempotency_key": "refund_second",
        })
        r2 = self.client.post(
            f"/api/v1/customers/{self.customer.id}/refund",
            data=payload2,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(r2.status_code, 409)
        self.assertEqual(r2.json()["error"], "Usage event already refunded")

    def test_refund_nonexistent_event_returns_404(self):
        import uuid
        response = self.client.post(
            f"/api/v1/customers/{self.customer.id}/refund",
            data=json.dumps({
                "usage_event_id": str(uuid.uuid4()),
                "reason": "Missing",
                "idempotency_key": "refund_missing",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 404)


class RecordUsageRawMetricsEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Test Tenant")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_raw",
        )
        wallet = self.customer.wallet
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])
        ProviderRate.objects.create(
            provider="google_gemini",
            event_type="gemini_api_call",
            metric_name="input_tokens",
            dimensions={"model": "gemini-2.0-flash"},
            cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
        )

    def test_record_usage_raw_metrics(self):
        response = self.client.post(
            "/api/v1/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_raw_1",
                "idempotency_key": "idem_raw_1",
                "event_type": "gemini_api_call",
                "provider": "google_gemini",
                "usage_metrics": {"input_tokens": 1_000_000},
                "properties": {"model": "gemini-2.0-flash"},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["provider_cost_micros"], 75_000)
        self.assertEqual(body["billed_cost_micros"], 75_000)

    def test_record_usage_negative_metrics_rejected(self):
        response = self.client.post(
            "/api/v1/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_neg",
                "idempotency_key": "idem_neg",
                "event_type": "gemini_api_call",
                "provider": "google_gemini",
                "usage_metrics": {"input_tokens": -100},
                "properties": {"model": "gemini-2.0-flash"},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 422)

    def test_record_usage_no_rate_returns_422(self):
        response = self.client.post(
            "/api/v1/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_norate",
                "idempotency_key": "idem_norate",
                "event_type": "unknown_type",
                "provider": "unknown",
                "usage_metrics": {"tokens": 100},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 422)

    def test_record_usage_both_modes_rejected(self):
        response = self.client.post(
            "/api/v1/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_both",
                "idempotency_key": "idem_both",
                "cost_micros": 100_000,
                "event_type": "gemini_api_call",
                "provider": "google_gemini",
                "usage_metrics": {"input_tokens": 100},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 422)
