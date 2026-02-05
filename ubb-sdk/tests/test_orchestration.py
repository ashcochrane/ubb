"""Tests for UBBClient product orchestration (Task 24).

Tests verify that UBBClient properly creates product clients based on
the metering/billing flags, and that the orchestrated record_usage and
pre_check methods correctly coordinate across product boundaries.
"""
import unittest
from unittest.mock import patch, MagicMock, PropertyMock
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
        self.assertIsNone(client.billing_client)
        client.close()

    def test_both_products_enabled(self):
        client = UBBClient(api_key="ubb_test_key", metering=True, billing=True)
        self.assertIsNotNone(client.metering)
        self.assertIsNotNone(client.billing_client)
        self.assertIsInstance(client.metering, MeteringClient)
        self.assertIsInstance(client.billing_client, BillingClient)
        client.close()

    def test_billing_only(self):
        client = UBBClient(api_key="ubb_test_key", metering=False, billing=True)
        self.assertIsNone(client.metering)
        self.assertIsNotNone(client.billing_client)
        client.close()

    def test_neither_product(self):
        client = UBBClient(api_key="ubb_test_key", metering=False, billing=False)
        self.assertIsNone(client.metering)
        self.assertIsNone(client.billing_client)
        client.close()

    def test_close_closes_product_clients(self):
        client = UBBClient(api_key="ubb_test_key", metering=True, billing=True)
        with patch.object(client.metering, "close") as mock_met_close, \
             patch.object(client.billing_client, "close") as mock_bill_close, \
             patch.object(client._http, "close"):
            client.close()
            mock_met_close.assert_called_once()
            mock_bill_close.assert_called_once()


class TestBackwardCompatibility(unittest.TestCase):
    """Test that existing UBBClient methods still work via the flat /api/v1/ endpoints."""

    def setUp(self):
        self.client = UBBClient(api_key="ubb_test_key")

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
    def test_record_usage_with_billing_debit(self, mock_met_request, mock_bill_request):
        """When billing is enabled, metering.record_usage is called and if
        billed_cost_micros > 0, billing.debit is also called."""
        # Mock metering response
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "event_id": "evt_1", "new_balance_micros": 8_500_000,
                "suspended": False, "billed_cost_micros": 1_500_000,
            }
        )
        # Mock billing debit response
        mock_bill_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "transaction_id": "txn_1", "balance_after_micros": 7_000_000,
            }
        )

        result = self.client.metering.record_usage(
            customer_id="cust_1", request_id="r1", idempotency_key="i1",
            cost_micros=1_500_000,
        )
        self.assertEqual(result.event_id, "evt_1")

        # Verify billing debit could also be called separately
        debit_result = self.client.billing_client.debit(
            customer_id="cust_1", amount_micros=1_500_000, reference="evt_1",
        )
        self.assertEqual(debit_result["balance_after_micros"], 7_000_000)

    @patch.object(MeteringClient, "_request")
    def test_record_usage_metering_only(self, mock_met_request):
        """When billing is enabled but billed_cost is 0, no debit call."""
        client = UBBClient(api_key="ubb_test_key", metering=True, billing=False)
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "event_id": "evt_2", "new_balance_micros": 10_000_000,
                "suspended": False, "billed_cost_micros": 0,
            }
        )
        result = client.metering.record_usage(
            customer_id="cust_1", request_id="r2", idempotency_key="i2",
            cost_micros=0,
        )
        self.assertEqual(result.event_id, "evt_2")
        self.assertIsNone(client.billing_client)
        client.close()


class TestOrchestratedPreCheck(unittest.TestCase):
    """Test the orchestrated pre_check that combines metering + billing."""

    def setUp(self):
        self.client = UBBClient(api_key="ubb_test_key", metering=True, billing=True)

    def tearDown(self):
        self.client.close()

    @patch.object(BillingClient, "_request")
    @patch.object(MeteringClient, "_request")
    def test_pre_check_with_billing(self, mock_met_request, mock_bill_request):
        """When both products are enabled, estimate_cost and billing pre_check
        can be called via the product clients."""
        # Mock metering estimate
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {"estimated_cost_micros": 750_000}
        )
        # Mock billing pre-check
        mock_bill_request.return_value = MagicMock(
            status_code=200, json=lambda: {"allowed": True, "reason": None}
        )

        estimated_cost = self.client.metering.estimate_cost(
            event_type="chat_completion", provider="openai",
            usage_metrics={"input_tokens": 100},
        )
        self.assertEqual(estimated_cost, 750_000)

        billing_check = self.client.billing_client.pre_check(
            customer_id="cust_1", estimated_cost=estimated_cost,
        )
        self.assertTrue(billing_check["allowed"])


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


if __name__ == "__main__":
    unittest.main()
