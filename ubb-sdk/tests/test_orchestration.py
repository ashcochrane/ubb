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
        client = UBBClient(api_key="ubb_test_key", max_retries=0)
        self.assertIsNotNone(client.metering)
        self.assertIsInstance(client.metering, MeteringClient)
        self.assertIsNone(client.billing)
        client.close()

    def test_both_products_enabled(self):
        client = UBBClient(api_key="ubb_test_key", max_retries=0, metering=True, billing=True)
        self.assertIsNotNone(client.metering)
        self.assertIsNotNone(client.billing)
        self.assertIsInstance(client.metering, MeteringClient)
        self.assertIsInstance(client.billing, BillingClient)
        client.close()

    def test_billing_only(self):
        client = UBBClient(api_key="ubb_test_key", max_retries=0, metering=False, billing=True)
        self.assertIsNone(client.metering)
        self.assertIsNotNone(client.billing)
        client.close()

    def test_neither_product(self):
        client = UBBClient(api_key="ubb_test_key", max_retries=0, metering=False, billing=False)
        self.assertIsNone(client.metering)
        self.assertIsNone(client.billing)
        client.close()

    def test_close_closes_product_clients(self):
        client = UBBClient(api_key="ubb_test_key", max_retries=0, metering=True, billing=True)
        with patch.object(client.metering, "close") as mock_met_close, \
             patch.object(client.billing, "close") as mock_bill_close:
            client.close()
            mock_met_close.assert_called_once()
            mock_bill_close.assert_called_once()


class TestPreCheckNoBilling(unittest.TestCase):
    """pre_check without billing returns trivially allowed."""

    def test_pre_check_no_billing_trivially_allowed(self):
        client = UBBClient(api_key="ubb_test_key", max_retries=0, metering=True, billing=False)
        result = client.pre_check(customer_id="cust_1")
        self.assertIsInstance(result, PreCheckResult)
        self.assertTrue(result.allowed)
        self.assertTrue(result.can_proceed)
        self.assertIsNone(result.balance_micros)
        client.close()

    def test_pre_check_with_billing_delegates(self):
        """With billing enabled, delegates to billing.pre_check."""
        client = UBBClient(api_key="ubb_test_key", max_retries=0, metering=True, billing=True)
        client.billing.pre_check = MagicMock(return_value={
            "allowed": True, "can_proceed": True, "balance_micros": 10_000_000,
        })
        result = client.pre_check(customer_id="cust_1")
        self.assertIsInstance(result, PreCheckResult)
        self.assertTrue(result.allowed)
        self.assertEqual(result.balance_micros, 10_000_000)
        client.billing.pre_check.assert_called_once_with(
            "cust_1", start_run=False, run_metadata=None, external_run_id="",
        )
        client.close()

    def test_widget_secret_and_tenant_id_preserved(self):
        client = UBBClient(
            api_key="ubb_test_key",
            widget_secret="secret123",
            tenant_id="tenant_1",
            max_retries=0,
        )
        self.assertEqual(client._widget_secret, "secret123")
        self.assertEqual(client._tenant_id, "tenant_1")
        client.close()


class TestOrchestratedRecordUsage(unittest.TestCase):
    """Test the orchestrated record_usage that combines metering + billing."""

    def setUp(self):
        self.client = UBBClient(api_key="ubb_test_key", max_retries=0, metering=True, billing=True)

    def tearDown(self):
        self.client.close()

    @patch.object(BillingClient, "_request")
    @patch.object(MeteringClient, "_request_usage")
    def test_record_usage_delegates_to_metering_no_double_debit(self, mock_met_request, mock_bill_request):
        """record_usage delegates to metering only — wallet deduction is
        handled server-side via the billing outbox handler, NOT by the SDK."""
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "event_id": "evt_1", "billed_cost_micros": 1_500_000,
            }
        )

        result = self.client.record_usage(
            customer_id="cust_1", request_id="r1", idempotency_key="i1",
            event_type="chat_completion", provider="openai",
            usage_metrics={"tokens": 100},
        )
        self.assertEqual(result.event_id, "evt_1")
        self.assertEqual(result.billed_cost_micros, 1_500_000)

        # Verify metering was called
        mock_met_request.assert_called_once()
        met_call = mock_met_request.call_args
        self.assertEqual(met_call.args[0], "post")
        self.assertEqual(met_call.args[1], "/api/v1/metering/usage")

        # billing.debit must NOT be called — server handles deduction
        mock_bill_request.assert_not_called()

    @patch.object(MeteringClient, "_request_usage")
    def test_record_usage_metering_only_no_debit_when_no_billing(self, mock_met_request):
        """When billing is not enabled, record_usage only calls metering."""
        client = UBBClient(api_key="ubb_test_key", max_retries=0, metering=True, billing=False)
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "event_id": "evt_2", "billed_cost_micros": 1_500_000,
            }
        )
        result = client.record_usage(
            customer_id="cust_1", request_id="r2", idempotency_key="i2",
            event_type="chat_completion", provider="openai",
            usage_metrics={"tokens": 100},
        )
        self.assertEqual(result.event_id, "evt_2")
        self.assertEqual(result.billed_cost_micros, 1_500_000)
        mock_met_request.assert_called_once()
        client.close()

    @patch.object(BillingClient, "_request")
    @patch.object(MeteringClient, "_request_usage")
    def test_record_usage_no_debit_when_billed_cost_is_zero(self, mock_met_request, mock_bill_request):
        """When billing is enabled but billed_cost is 0, no debit call."""
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "event_id": "evt_3", "billed_cost_micros": 0,
            }
        )
        result = self.client.record_usage(
            customer_id="cust_1", request_id="r3", idempotency_key="i3",
            event_type="test", provider="test",
            usage_metrics={"tokens": 1},
        )
        self.assertEqual(result.event_id, "evt_3")
        # billing debit should NOT have been called
        mock_bill_request.assert_not_called()

    @patch.object(BillingClient, "_request")
    @patch.object(MeteringClient, "_request_usage")
    def test_record_usage_no_debit_when_billed_cost_is_none(self, mock_met_request, mock_bill_request):
        """When billing is enabled but billed_cost is None, no debit call."""
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "event_id": "evt_4",
            }
        )
        result = self.client.record_usage(
            customer_id="cust_1", request_id="r4", idempotency_key="i4",
            event_type="test", provider="test",
            usage_metrics={"tokens": 1},
        )
        self.assertEqual(result.event_id, "evt_4")
        mock_bill_request.assert_not_called()

    def test_record_usage_requires_metering(self):
        """record_usage raises UBBError when metering is not enabled."""
        from ubb.exceptions import UBBError
        client = UBBClient(api_key="ubb_test_key", max_retries=0, metering=False, billing=True)
        with self.assertRaises(UBBError):
            client.record_usage(customer_id="c1", request_id="r1", idempotency_key="i1",
                                event_type="test", provider="test", usage_metrics={"tokens": 1})
        client.close()


class TestOrchestratedPreCheck(unittest.TestCase):
    """Test the orchestrated pre_check that delegates to billing."""

    def setUp(self):
        self.client = UBBClient(api_key="ubb_test_key", max_retries=0, metering=True, billing=True)

    def tearDown(self):
        self.client.close()

    @patch.object(BillingClient, "_request")
    def test_pre_check_delegates_to_billing(self, mock_bill_request):
        """pre_check delegates to billing.pre_check."""
        mock_bill_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "allowed": True, "reason": None,
                "balance_micros": 10_000_000,
            }
        )
        result = self.client.pre_check(customer_id="cust_1")
        self.assertIsInstance(result, PreCheckResult)
        self.assertTrue(result.allowed)
        self.assertTrue(result.can_proceed)
        self.assertEqual(result.balance_micros, 10_000_000)
        mock_bill_request.assert_called_once()

    @patch.object(BillingClient, "_request")
    def test_pre_check_billing_denies(self, mock_bill_request):
        """When billing denies the pre-check, result reflects that."""
        mock_bill_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "allowed": False, "reason": "insufficient_funds",
                "balance_micros": -6_000_000,
            }
        )
        result = self.client.pre_check(customer_id="cust_1")
        self.assertFalse(result.allowed)
        self.assertFalse(result.can_proceed)
        self.assertEqual(result.balance_micros, -6_000_000)

    def test_pre_check_no_billing_trivially_allowed(self):
        """Without billing, pre_check returns trivially allowed."""
        client = UBBClient(api_key="ubb_test_key", max_retries=0, metering=True, billing=False)
        result = client.pre_check(customer_id="cust_1")
        self.assertTrue(result.allowed)
        self.assertTrue(result.can_proceed)
        self.assertIsNone(result.balance_micros)
        client.close()


class TestRecordUsageResultFields(unittest.TestCase):
    """Test that RecordUsageResult supports server-side pricing fields."""

    def test_result_with_pricing_fields(self):
        result = RecordUsageResult(
            event_id="evt_1",
            provider_cost_micros=500_000,
            billed_cost_micros=1_000_000,
        )
        self.assertEqual(result.provider_cost_micros, 500_000)
        self.assertEqual(result.billed_cost_micros, 1_000_000)

    def test_result_minimal(self):
        result = RecordUsageResult(
            event_id="evt_1",
        )
        self.assertIsNone(result.provider_cost_micros)
        self.assertIsNone(result.billed_cost_micros)


class TestPreCheckResultFields(unittest.TestCase):
    """Test that PreCheckResult supports the correct fields."""

    def test_result_with_all_fields(self):
        result = PreCheckResult(
            allowed=True,
            can_proceed=True,
            balance_micros=10_000_000,
        )
        self.assertTrue(result.allowed)
        self.assertTrue(result.can_proceed)
        self.assertEqual(result.balance_micros, 10_000_000)

    def test_result_legacy_fields_only(self):
        result = PreCheckResult(allowed=True, reason=None)
        self.assertTrue(result.allowed)
        self.assertIsNone(result.can_proceed)
        self.assertIsNone(result.balance_micros)


if __name__ == "__main__":
    unittest.main()
