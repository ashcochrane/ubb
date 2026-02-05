"""Tests for UBBClient product orchestration.

Tests verify that UBBClient properly creates product clients based on
the metering/billing flags, and that the orchestrated record_usage and
pre_check methods correctly coordinate across product boundaries.
"""
import unittest
from unittest.mock import patch, MagicMock
from ubb.client import UBBClient
from ubb.metering import MeteringClient
from ubb.billing import BillingClient
from ubb.types import RecordUsageResult, PreCheckResult


class TestProductClientCreation(unittest.TestCase):
    """Test that UBBClient creates the right product clients based on flags."""

    def test_default_creates_metering_only(self):
        client = UBBClient(api_key="ubb_test_key")
        self.assertIsNotNone(client.metering)
        self.assertIsInstance(client.metering, MeteringClient)
        self.assertIsNone(client.billing)
        # Backward compat alias
        self.assertIsNone(client.billing_client)
        client.close()

    def test_both_products_enabled(self):
        client = UBBClient(api_key="ubb_test_key", metering=True, billing=True)
        self.assertIsNotNone(client.metering)
        self.assertIsNotNone(client.billing)
        self.assertIsInstance(client.metering, MeteringClient)
        self.assertIsInstance(client.billing, BillingClient)
        # Backward compat alias
        self.assertIs(client.billing, client.billing_client)
        client.close()

    def test_billing_only(self):
        client = UBBClient(api_key="ubb_test_key", metering=False, billing=True)
        self.assertIsNone(client.metering)
        self.assertIsNotNone(client.billing)
        self.assertIsNotNone(client.billing_client)
        client.close()

    def test_neither_product(self):
        client = UBBClient(api_key="ubb_test_key", metering=False, billing=False)
        self.assertIsNone(client.metering)
        self.assertIsNone(client.billing)
        self.assertIsNone(client.billing_client)
        client.close()

    def test_close_closes_product_clients(self):
        client = UBBClient(api_key="ubb_test_key", metering=True, billing=True)
        with patch.object(client.metering, "close") as mock_met_close, \
             patch.object(client.billing, "close") as mock_bill_close, \
             patch.object(client._http, "close"):
            client.close()
            mock_met_close.assert_called_once()
            mock_bill_close.assert_called_once()


class TestBackwardCompatibility(unittest.TestCase):
    """Test that existing UBBClient methods still work via the flat /api/v1/ endpoints."""

    def setUp(self):
        # metering=False forces legacy fallback path for record_usage and pre_check
        self.client = UBBClient(api_key="ubb_test_key", metering=False, billing=False)

    def tearDown(self):
        self.client.close()

    @patch("ubb.client.httpx.Client.post")
    def test_legacy_pre_check_uses_flat_endpoint(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"allowed": True, "reason": None}
        )
        result = self.client.pre_check(customer_id="cust_1")
        self.assertIsInstance(result, PreCheckResult)
        self.assertTrue(result.allowed)
        call_args = mock_post.call_args
        self.assertEqual(call_args.args[0], "/api/v1/pre-check")

    @patch("ubb.client.httpx.Client.post")
    def test_legacy_pre_check_without_event_type_uses_flat_endpoint(self, mock_post):
        """Even with metering enabled, if no event_type is given, falls back to legacy."""
        client = UBBClient(api_key="ubb_test_key", metering=True, billing=True)
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"allowed": True, "reason": None}
        )
        result = client.pre_check(customer_id="cust_1")
        self.assertIsInstance(result, PreCheckResult)
        self.assertTrue(result.allowed)
        # Should have called the flat endpoint on the UBBClient's own _http
        call_args = mock_post.call_args
        self.assertEqual(call_args.args[0], "/api/v1/pre-check")
        client.close()

    @patch("ubb.client.httpx.Client.post")
    def test_legacy_record_usage_uses_flat_endpoint(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {
                "event_id": "evt_1", "new_balance_micros": 8_500_000, "suspended": False,
            }
        )
        result = self.client.record_usage(
            customer_id="c1", request_id="r1", idempotency_key="i1", cost_micros=1_500_000,
        )
        self.assertIsInstance(result, RecordUsageResult)
        call_args = mock_post.call_args
        self.assertEqual(call_args.args[0], "/api/v1/usage")

    @patch("ubb.client.httpx.Client.get")
    def test_legacy_get_balance_uses_flat_endpoint(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200, json=lambda: {"balance_micros": 10_000_000, "currency": "USD"}
        )
        result = self.client.get_balance(customer_id="c1")
        call_args = mock_get.call_args
        self.assertEqual(call_args.args[0], "/api/v1/customers/c1/balance")

    def test_widget_secret_and_tenant_id_preserved(self):
        client = UBBClient(
            api_key="ubb_test_key",
            widget_secret="secret123",
            tenant_id="tenant_1",
        )
        self.assertEqual(client._widget_secret, "secret123")
        self.assertEqual(client._tenant_id, "tenant_1")
        client.close()


class TestOrchestratedRecordUsage(unittest.TestCase):
    """Test the orchestrated record_usage that combines metering + billing."""

    def setUp(self):
        self.client = UBBClient(api_key="ubb_test_key", metering=True, billing=True)

    def tearDown(self):
        self.client.close()

    @patch.object(BillingClient, "_request")
    @patch.object(MeteringClient, "_request")
    def test_record_usage_delegates_to_metering_and_debits_billing(self, mock_met_request, mock_bill_request):
        """When both metering and billing are enabled, record_usage calls
        metering.record_usage and then billing.debit when billed_cost_micros > 0."""
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "event_id": "evt_1", "new_balance_micros": 8_500_000,
                "suspended": False, "billed_cost_micros": 1_500_000,
            }
        )
        mock_bill_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "new_balance_micros": 7_000_000, "transaction_id": "txn_1",
            }
        )

        result = self.client.record_usage(
            customer_id="cust_1", request_id="r1", idempotency_key="i1",
            cost_micros=1_500_000,
        )
        self.assertEqual(result.event_id, "evt_1")
        self.assertEqual(result.billed_cost_micros, 1_500_000)
        self.assertEqual(result.balance_after_micros, 7_000_000)

        # Verify metering was called
        mock_met_request.assert_called_once()
        met_call = mock_met_request.call_args
        self.assertEqual(met_call.args[0], "post")
        self.assertEqual(met_call.args[1], "/api/v1/metering/usage")

        # Verify billing debit was called
        mock_bill_request.assert_called_once()
        bill_call = mock_bill_request.call_args
        self.assertEqual(bill_call.args[0], "post")
        self.assertEqual(bill_call.args[1], "/api/v1/billing/debit")

    @patch.object(MeteringClient, "_request")
    def test_record_usage_metering_only_no_debit_when_no_billing(self, mock_met_request):
        """When billing is not enabled, record_usage only calls metering."""
        client = UBBClient(api_key="ubb_test_key", metering=True, billing=False)
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "event_id": "evt_2", "new_balance_micros": 10_000_000,
                "suspended": False, "billed_cost_micros": 1_500_000,
            }
        )
        result = client.record_usage(
            customer_id="cust_1", request_id="r2", idempotency_key="i2",
            cost_micros=1_500_000,
        )
        self.assertEqual(result.event_id, "evt_2")
        # balance_after_micros not set because no billing debit
        self.assertIsNone(result.balance_after_micros)
        mock_met_request.assert_called_once()
        client.close()

    @patch.object(BillingClient, "_request")
    @patch.object(MeteringClient, "_request")
    def test_record_usage_no_debit_when_billed_cost_is_zero(self, mock_met_request, mock_bill_request):
        """When billing is enabled but billed_cost is 0, no debit call."""
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "event_id": "evt_3", "new_balance_micros": 10_000_000,
                "suspended": False, "billed_cost_micros": 0,
            }
        )
        result = self.client.record_usage(
            customer_id="cust_1", request_id="r3", idempotency_key="i3",
            cost_micros=0,
        )
        self.assertEqual(result.event_id, "evt_3")
        # billing debit should NOT have been called
        mock_bill_request.assert_not_called()
        self.assertIsNone(result.balance_after_micros)

    @patch.object(BillingClient, "_request")
    @patch.object(MeteringClient, "_request")
    def test_record_usage_no_debit_when_billed_cost_is_none(self, mock_met_request, mock_bill_request):
        """When billing is enabled but billed_cost is None, no debit call."""
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "event_id": "evt_4", "new_balance_micros": 10_000_000,
                "suspended": False,
            }
        )
        result = self.client.record_usage(
            customer_id="cust_1", request_id="r4", idempotency_key="i4",
            cost_micros=500_000,
        )
        self.assertEqual(result.event_id, "evt_4")
        mock_bill_request.assert_not_called()


class TestOrchestratedPreCheck(unittest.TestCase):
    """Test the orchestrated pre_check that combines metering + billing."""

    def setUp(self):
        self.client = UBBClient(api_key="ubb_test_key", metering=True, billing=True)

    def tearDown(self):
        self.client.close()

    @patch.object(BillingClient, "_request")
    @patch.object(MeteringClient, "_request")
    def test_pre_check_orchestrates_metering_and_billing(self, mock_met_request, mock_bill_request):
        """When event_type is provided, pre_check estimates cost via metering
        then checks billing eligibility."""
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {"estimated_cost_micros": 750_000}
        )
        mock_bill_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "allowed": True, "can_proceed": True,
                "balance_micros": 10_000_000, "reason": None,
            }
        )

        result = self.client.pre_check(
            customer_id="cust_1",
            event_type="chat_completion",
            provider="openai",
            usage_metrics={"input_tokens": 100},
        )
        self.assertIsInstance(result, PreCheckResult)
        self.assertTrue(result.allowed)
        self.assertTrue(result.can_proceed)
        self.assertEqual(result.estimated_cost_micros, 750_000)
        self.assertEqual(result.balance_micros, 10_000_000)

        # Verify metering estimate was called
        mock_met_request.assert_called_once()
        # Verify billing pre-check was called
        mock_bill_request.assert_called_once()

    @patch.object(MeteringClient, "_request")
    def test_pre_check_metering_only_no_billing(self, mock_met_request):
        """When billing is not enabled, pre_check still estimates cost but
        returns can_proceed=True without billing check."""
        client = UBBClient(api_key="ubb_test_key", metering=True, billing=False)
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {"estimated_cost_micros": 500_000}
        )
        result = client.pre_check(
            customer_id="cust_1",
            event_type="chat_completion",
            provider="openai",
            usage_metrics={"input_tokens": 50},
        )
        self.assertTrue(result.allowed)
        self.assertTrue(result.can_proceed)
        self.assertEqual(result.estimated_cost_micros, 500_000)
        self.assertIsNone(result.balance_micros)
        client.close()

    @patch.object(BillingClient, "_request")
    @patch.object(MeteringClient, "_request")
    def test_pre_check_billing_denies(self, mock_met_request, mock_bill_request):
        """When billing denies the pre-check, result reflects that."""
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {"estimated_cost_micros": 5_000_000}
        )
        mock_bill_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "allowed": False, "can_proceed": False,
                "balance_micros": 1_000_000, "reason": "Insufficient balance",
            }
        )
        result = self.client.pre_check(
            customer_id="cust_1",
            event_type="chat_completion",
            provider="openai",
            usage_metrics={"input_tokens": 1000},
        )
        self.assertFalse(result.allowed)
        self.assertFalse(result.can_proceed)
        self.assertEqual(result.estimated_cost_micros, 5_000_000)
        self.assertEqual(result.balance_micros, 1_000_000)


class TestRecordUsageResultBalanceAfter(unittest.TestCase):
    """Test that RecordUsageResult now supports optional balance_after_micros."""

    def test_result_with_balance_after(self):
        result = RecordUsageResult(
            event_id="evt_1",
            new_balance_micros=8_500_000,
            suspended=False,
            balance_after_micros=7_000_000,
        )
        self.assertEqual(result.balance_after_micros, 7_000_000)

    def test_result_without_balance_after(self):
        result = RecordUsageResult(
            event_id="evt_1",
            new_balance_micros=8_500_000,
            suspended=False,
        )
        self.assertIsNone(result.balance_after_micros)


class TestPreCheckResultFields(unittest.TestCase):
    """Test that PreCheckResult supports new orchestration fields."""

    def test_result_with_all_fields(self):
        result = PreCheckResult(
            allowed=True,
            can_proceed=True,
            estimated_cost_micros=750_000,
            balance_micros=10_000_000,
        )
        self.assertTrue(result.allowed)
        self.assertTrue(result.can_proceed)
        self.assertEqual(result.estimated_cost_micros, 750_000)
        self.assertEqual(result.balance_micros, 10_000_000)

    def test_result_legacy_fields_only(self):
        result = PreCheckResult(allowed=True, reason=None)
        self.assertTrue(result.allowed)
        self.assertIsNone(result.can_proceed)
        self.assertIsNone(result.estimated_cost_micros)
        self.assertIsNone(result.balance_micros)


if __name__ == "__main__":
    unittest.main()
