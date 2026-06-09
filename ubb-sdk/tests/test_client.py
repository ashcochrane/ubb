"""Tests for UBBClient convenience methods (delegation model).

These tests verify that UBBClient's convenience methods properly delegate
to the underlying product clients. The UBBClient no longer has its own
_http client -- all HTTP calls go through product clients.
"""
import unittest
from unittest.mock import patch, MagicMock

from ubb.client import UBBClient, _check_micros
from ubb.exceptions import (
    UBBError, UBBValidationError,
)
from ubb.metering import MeteringClient
from ubb.billing import BillingClient
from ubb.types import (
    PreCheckResult, RecordUsageResult, CustomerResult, BalanceResult,
    UsageEvent, TopUpResult, AutoTopUpResult, WithdrawResult, RefundResult,
    WalletTransaction, PaginatedResponse,
)


class UBBClientTest(unittest.TestCase):
    def setUp(self):
        self.client = UBBClient(api_key="ubb_live_test123",
                                base_url="http://localhost:8001",
                                metering=True, billing=True)

    def tearDown(self):
        self.client.close()

    # --- pre_check (delegates to metering + billing) ---

    def test_pre_check_metering_only_no_event_type(self):
        """Without event_type and no billing, pre_check returns trivially allowed."""
        client = UBBClient(api_key="test", metering=True, billing=False)
        result = client.pre_check(customer_id="cust_123")
        self.assertTrue(result.allowed)
        self.assertTrue(result.can_proceed)
        client.close()

    def test_pre_check_with_billing_delegates(self):
        """With billing, pre_check delegates to billing.pre_check."""
        self.client.billing.pre_check = MagicMock(return_value={
            "allowed": True, "can_proceed": True, "balance_micros": 10_000_000,
        })
        result = self.client.pre_check(customer_id="cust_123")
        self.assertTrue(result.allowed)
        self.client.billing.pre_check.assert_called_once_with(
            "cust_123", start_run=False, run_metadata=None, external_run_id="",
        )

    # --- record_usage (delegates to metering) ---

    @patch.object(MeteringClient, "_request_usage")
    def test_record_usage(self, mock_met_request):
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "event_id": "evt_1", "new_balance_micros": 8500000, "suspended": False,
            }
        )
        result = self.client.record_usage(
            customer_id="c1", request_id="r1", idempotency_key="i1", provider_cost_micros=1500000,
        )
        self.assertEqual(result.new_balance_micros, 8500000)
        self.assertFalse(result.suspended)

    # --- create_customer (uses metering._request for platform API) ---

    def test_create_customer(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "c1", "external_id": "u42", "status": "active",
        }
        self.client.metering._request = MagicMock(return_value=mock_response)
        result = self.client.create_customer(external_id="u42",
                                             stripe_customer_id="cus_abc")
        self.assertEqual(result.external_id, "u42")
        self.client.metering._request.assert_called_once_with(
            "post", "/api/v1/platform/customers", json={
                "external_id": "u42",
                "stripe_customer_id": "cus_abc",
                "metadata": {},
                "account_type": "individual",
                "parent_external_id": "",
                "billing_topology": "",
            }
        )

    # --- get_balance (delegates to billing) ---

    def test_get_balance(self):
        expected = BalanceResult(balance_micros=10000000, currency="USD")
        self.client.billing.get_balance = MagicMock(return_value=expected)
        result = self.client.get_balance(customer_id="c1")
        self.assertEqual(result.balance_micros, 10000000)
        self.client.billing.get_balance.assert_called_once_with("c1")

    # --- Billing-required methods raise UBBError when billing disabled ---

    def test_get_balance_raises_without_billing(self):
        client = UBBClient(api_key="test", metering=True, billing=False)
        with self.assertRaises(UBBError):
            client.get_balance("c1")
        client.close()

    # --- Context manager ---

    def test_context_manager(self):
        with patch.object(self.client, "close") as mock_close:
            with self.client:
                pass
            mock_close.assert_called_once()

    # --- Client-side validation (module-level functions) ---

    def test_check_micros_rejects_zero(self):
        with self.assertRaises(UBBValidationError):
            _check_micros(0, "cost_micros")

    def test_check_micros_rejects_negative(self):
        with self.assertRaises(UBBValidationError):
            _check_micros(-10_000, "cost_micros")

    # --- get_usage (delegates to metering) ---

    def test_get_usage(self):
        expected = PaginatedResponse(
            data=[UsageEvent(id="e1", request_id="r1", billed_cost_micros=10000,
                             metadata={}, effective_at="2025-01-01T00:00:00Z")],
            next_cursor="cur_abc", has_more=True,
        )
        self.client.metering.get_usage = MagicMock(return_value=expected)
        result = self.client.get_usage(customer_id="c1")
        self.assertIsInstance(result, PaginatedResponse)
        self.assertEqual(len(result.data), 1)
        self.assertTrue(result.has_more)
        self.assertEqual(result.next_cursor, "cur_abc")

    def test_get_usage_with_cursor(self):
        expected = PaginatedResponse(data=[], next_cursor=None, has_more=False)
        self.client.metering.get_usage = MagicMock(return_value=expected)
        self.client.get_usage(customer_id="c1", cursor="cur_abc", limit=10)
        self.client.metering.get_usage.assert_called_once_with(
            "c1", cursor="cur_abc", limit=10,
        )

    # --- create_top_up (delegates to billing) ---

    def test_create_top_up(self):
        expected = TopUpResult(checkout_url="https://checkout.example.com/abc")
        self.client.billing.create_top_up = MagicMock(return_value=expected)
        result = self.client.create_top_up(customer_id="c1", amount_micros=50_000,
                                           success_url="http://ok", cancel_url="http://no")
        self.assertIsInstance(result, TopUpResult)
        self.assertEqual(result.checkout_url, "https://checkout.example.com/abc")

    # --- configure_auto_top_up (delegates to billing) ---

    def test_configure_auto_top_up(self):
        self.client.billing.configure_auto_topup = MagicMock(
            return_value={"status": "enabled"}
        )
        result = self.client.configure_auto_top_up(customer_id="c1", threshold=0,
                                                   amount=100_000)
        self.assertIsInstance(result, AutoTopUpResult)
        self.assertEqual(result.status, "enabled")

    # --- withdraw (delegates to billing.debit) ---

    def test_withdraw(self):
        self.client.billing.debit = MagicMock(
            return_value={"transaction_id": "txn_1", "new_balance_micros": 5000000}
        )
        result = self.client.withdraw(customer_id="c1", amount_micros=10_000,
                                      idempotency_key="w1")
        self.assertIsInstance(result, WithdrawResult)
        self.assertEqual(result.transaction_id, "txn_1")
        self.assertEqual(result.balance_micros, 5000000)

    # --- refund_usage (delegates to billing.credit) ---

    def test_refund_usage(self):
        self.client.billing.credit = MagicMock(
            return_value={"transaction_id": "ref_1", "new_balance_micros": 11000000}
        )
        result = self.client.refund_usage(
            customer_id="c1", usage_event_id="evt_1", idempotency_key="rf1", reason="mistake",
        )
        self.assertIsInstance(result, RefundResult)
        self.assertEqual(result.refund_id, "ref_1")

    # --- get_transactions (delegates to billing) ---

    def test_get_transactions(self):
        expected = PaginatedResponse(
            data=[WalletTransaction(
                id="t1", transaction_type="top_up", amount_micros=100000,
                balance_after_micros=200000, description="Top up",
                reference_id="ref_1", created_at="2025-01-01T00:00:00Z",
            )],
            next_cursor=None, has_more=False,
        )
        self.client.billing.get_transactions = MagicMock(return_value=expected)
        result = self.client.get_transactions(customer_id="c1")
        self.assertIsInstance(result, PaginatedResponse)
        self.assertEqual(len(result.data), 1)
        self.assertFalse(result.has_more)

    # --- close ---

    def test_close(self):
        with patch.object(self.client.metering, "close") as mock_met_close, \
             patch.object(self.client.billing, "close") as mock_bill_close:
            self.client.close()
            mock_met_close.assert_called_once()
            mock_bill_close.assert_called_once()


class TenantConfigClientTest(unittest.TestCase):
    """Tests for UBBClient.get_tenant_config and update_tenant_config."""

    CONFIG_FIXTURE = {
        "name": "TestTenant",
        "billing_mode": "meter_only",
        "products": ["metering"],
        "require_cost_card_coverage": False,
        "default_currency": "usd",
        "stripe_connected_account_id": "acct_test",
        "is_active": True,
    }

    def setUp(self):
        self.client = UBBClient(api_key="ubb_live_test", base_url="http://localhost:8001",
                                metering=True, billing=False)

    def tearDown(self):
        self.client.close()

    def test_get_tenant_config_calls_correct_endpoint(self):
        mock_resp = MagicMock(status_code=200, json=lambda: self.CONFIG_FIXTURE)
        self.client.metering._request = MagicMock(return_value=mock_resp)
        result = self.client.get_tenant_config()
        self.client.metering._request.assert_called_once_with("get", "/api/v1/tenant/config")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["billing_mode"], "meter_only")
        self.assertIn("metering", result["products"])

    def test_update_tenant_config_sends_only_non_none_fields(self):
        updated = {**self.CONFIG_FIXTURE, "billing_mode": "postpaid", "products": ["metering", "billing"]}
        mock_resp = MagicMock(status_code=200, json=lambda: updated)
        self.client.metering._request = MagicMock(return_value=mock_resp)
        result = self.client.update_tenant_config(billing_mode="postpaid",
                                                   products=["metering", "billing"])
        self.client.metering._request.assert_called_once_with(
            "patch", "/api/v1/tenant/config",
            json={"billing_mode": "postpaid", "products": ["metering", "billing"]},
        )
        self.assertIsInstance(result, dict)
        self.assertEqual(result["billing_mode"], "postpaid")

    def test_update_tenant_config_omits_none_fields(self):
        """Only require_cost_card_coverage=True is set; billing_mode and products are omitted."""
        updated = {**self.CONFIG_FIXTURE, "require_cost_card_coverage": True}
        mock_resp = MagicMock(status_code=200, json=lambda: updated)
        self.client.metering._request = MagicMock(return_value=mock_resp)
        self.client.update_tenant_config(require_cost_card_coverage=True)
        self.client.metering._request.assert_called_once_with(
            "patch", "/api/v1/tenant/config",
            json={"require_cost_card_coverage": True},
        )

    def test_update_tenant_config_empty_call_sends_empty_body(self):
        """Calling with no args sends an empty body."""
        mock_resp = MagicMock(status_code=200, json=lambda: self.CONFIG_FIXTURE)
        self.client.metering._request = MagicMock(return_value=mock_resp)
        self.client.update_tenant_config()
        self.client.metering._request.assert_called_once_with(
            "patch", "/api/v1/tenant/config", json={},
        )


class ConnectClientTest(unittest.TestCase):
    """Tests for UBBClient.start_connect_onboarding and get_connect_status."""

    def setUp(self):
        self.client = UBBClient(api_key="ubb_live_test", base_url="http://localhost:8001",
                                metering=True, billing=False)

    def tearDown(self):
        self.client.close()

    def test_start_connect_onboarding_calls_correct_endpoint(self):
        mock_resp = MagicMock(
            status_code=200,
            json=lambda: {"authorize_url": "https://connect.stripe.com/oauth/authorize?x=1"},
        )
        self.client.metering._request = MagicMock(return_value=mock_resp)
        result = self.client.start_connect_onboarding(return_url="https://x/done")
        self.client.metering._request.assert_called_once_with(
            "post", "/api/v1/connect/start", json={"return_url": "https://x/done"},
        )
        self.assertIsInstance(result, dict)
        self.assertTrue(result["authorize_url"].startswith("https://connect.stripe.com"))

    def test_start_connect_onboarding_defaults_empty_return_url(self):
        mock_resp = MagicMock(status_code=200, json=lambda: {"authorize_url": "https://c/x"})
        self.client.metering._request = MagicMock(return_value=mock_resp)
        self.client.start_connect_onboarding()
        self.client.metering._request.assert_called_once_with(
            "post", "/api/v1/connect/start", json={"return_url": ""},
        )

    def test_get_connect_status_calls_correct_endpoint(self):
        mock_resp = MagicMock(
            status_code=200,
            json=lambda: {"account_id": "acct_x", "charges_enabled": True, "onboarded": True},
        )
        self.client.metering._request = MagicMock(return_value=mock_resp)
        result = self.client.get_connect_status()
        self.client.metering._request.assert_called_once_with("get", "/api/v1/connect/status")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["account_id"], "acct_x")
        self.assertTrue(result["onboarded"])


class SubscriptionOrchestrationClientTest(unittest.TestCase):
    """Tests for UBBClient.create_plan / subscribe_customer / set_seats."""

    def setUp(self):
        self.client = UBBClient(api_key="ubb_live_test", base_url="http://localhost:8001",
                                metering=True, billing=False)

    def tearDown(self):
        self.client.close()

    def test_create_plan(self):
        plan = {
            "id": "p1", "key": "pro", "name": "Pro",
            "access_fee_micros": 50_000_000, "per_seat_micros": 8_000_000,
            "interval": "month", "usage_mode": "invoice_item",
        }
        mock_resp = MagicMock(status_code=201, json=lambda: plan)
        self.client.metering._request = MagicMock(return_value=mock_resp)
        result = self.client.create_plan(
            "pro", "Pro", access_fee_micros=50_000_000, per_seat_micros=8_000_000,
        )
        self.client.metering._request.assert_called_once_with(
            "post", "/api/v1/platform/plans", json={
                "key": "pro",
                "name": "Pro",
                "access_fee_micros": 50_000_000,
                "per_seat_micros": 8_000_000,
                "interval": "month",
                "usage_mode": "invoice_item",
            },
        )
        self.assertEqual(result["key"], "pro")

    def test_subscribe_customer(self):
        mock_resp = MagicMock(
            status_code=200,
            json=lambda: {"subscription_id": "sub_1", "amount_micros": 130_000_000, "quantity": 10},
        )
        self.client.metering._request = MagicMock(return_value=mock_resp)
        result = self.client.subscribe_customer("biz", "pro", seats=10)
        self.client.metering._request.assert_called_once_with(
            "post", "/api/v1/platform/customers/biz/subscribe",
            json={"plan_key": "pro", "seats": 10},
        )
        self.assertEqual(result["subscription_id"], "sub_1")
        self.assertEqual(result["quantity"], 10)

    def test_set_seats(self):
        mock_resp = MagicMock(status_code=200, json=lambda: {"seats": 12})
        self.client.metering._request = MagicMock(return_value=mock_resp)
        result = self.client.set_seats("biz", 12)
        self.client.metering._request.assert_called_once_with(
            "post", "/api/v1/platform/customers/biz/seats",
            json={"seats": 12},
        )
        self.assertEqual(result["seats"], 12)


if __name__ == "__main__":
    unittest.main()
