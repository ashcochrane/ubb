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
from ubb.types import PreCheckResult
from ubb._core.models.record_usage_response import RecordUsageResponse


class TestProductClientCreation(unittest.TestCase):
    """Test that UBBClient creates the right product clients based on flags."""

    def test_default_creates_metering_only(self):
        client = UBBClient(api_key="ubb_test_key")
        self.assertIsNotNone(client.metering)
        self.assertIsInstance(client.metering, MeteringClient)
        self.assertIsNone(client.billing)
        client.close()

    def test_both_products_enabled(self):
        client = UBBClient(api_key="ubb_test_key", metering=True, billing=True)
        self.assertIsNotNone(client.metering)
        self.assertIsNotNone(client.billing)
        self.assertIsInstance(client.metering, MeteringClient)
        self.assertIsInstance(client.billing, BillingClient)
        client.close()

    def test_billing_only(self):
        client = UBBClient(api_key="ubb_test_key", metering=False, billing=True)
        self.assertIsNone(client.metering)
        self.assertIsNotNone(client.billing)
        client.close()

    def test_neither_product(self):
        client = UBBClient(api_key="ubb_test_key", metering=False, billing=False)
        self.assertIsNone(client.metering)
        self.assertIsNone(client.billing)
        client.close()

    def test_close_closes_product_clients(self):
        client = UBBClient(api_key="ubb_test_key", metering=True, billing=True)
        with patch.object(client.metering, "close") as mock_met_close, \
             patch.object(client.billing, "close") as mock_bill_close:
            client.close()
            mock_met_close.assert_called_once()
            mock_bill_close.assert_called_once()


class TestPreCheckNoBilling(unittest.TestCase):
    """pre_check without billing returns trivially allowed."""

    def test_pre_check_no_billing_trivially_allowed(self):
        client = UBBClient(api_key="ubb_test_key", metering=True, billing=False)
        result = client.pre_check(customer_id="cust_1")
        self.assertIsInstance(result, PreCheckResult)
        self.assertTrue(result.allowed)
        self.assertTrue(result.can_proceed)
        self.assertIsNone(result.balance_micros)
        client.close()

    def test_pre_check_with_billing_delegates(self):
        """With billing enabled, delegates to billing.pre_check."""
        client = UBBClient(api_key="ubb_test_key", metering=True, billing=True)
        client.billing.pre_check = MagicMock(return_value={
            "allowed": True, "can_proceed": True, "balance_micros": 10_000_000,
        })
        result = client.pre_check(customer_id="cust_1")
        self.assertIsInstance(result, PreCheckResult)
        self.assertTrue(result.allowed)
        self.assertEqual(result.balance_micros, 10_000_000)
        client.billing.pre_check.assert_called_once_with(
            "cust_1", parent_task_id=None,
        )
        client.close()

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
    def test_record_usage_delegates_to_metering_no_double_debit(self, mock_met_request, mock_bill_request):
        """record_usage delegates to metering only — wallet deduction is
        handled server-side via the billing outbox handler, NOT by the SDK."""
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "event_id": "evt_1", "new_balance_micros": 8_500_000,
                "suspended": False, "costing_status": "known", "pricing_status": "known",
                "billed_cost_micros": 1_500_000,
            }
        )

        result = self.client.record_usage(
            customer_id="cust_1", idempotency_key="i1",
            provider_cost_micros=1_500_000,
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

    @patch.object(MeteringClient, "_request")
    def test_record_usage_metering_only_no_debit_when_no_billing(self, mock_met_request):
        """When billing is not enabled, record_usage only calls metering."""
        client = UBBClient(api_key="ubb_test_key", metering=True, billing=False)
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "event_id": "evt_2", "new_balance_micros": 10_000_000,
                "suspended": False, "costing_status": "known", "pricing_status": "known",
                "billed_cost_micros": 1_500_000,
            }
        )
        result = client.record_usage(
            customer_id="cust_1", idempotency_key="i2",
            provider_cost_micros=1_500_000,
        )
        self.assertEqual(result.event_id, "evt_2")
        # (balance_after_micros retired: not in the RecordUsageResponse contract.)
        mock_met_request.assert_called_once()
        client.close()

    @patch.object(BillingClient, "_request")
    @patch.object(MeteringClient, "_request")
    def test_record_usage_no_debit_when_billed_cost_is_zero(self, mock_met_request, mock_bill_request):
        """When billing is enabled but billed_cost is 0, no debit call."""
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "event_id": "evt_3", "new_balance_micros": 10_000_000,
                "suspended": False, "costing_status": "known", "pricing_status": "known",
                "billed_cost_micros": 0,
            }
        )
        result = self.client.record_usage(
            customer_id="cust_1", idempotency_key="i3",
            provider_cost_micros=0,
        )
        self.assertEqual(result.event_id, "evt_3")
        # billing debit should NOT have been called
        mock_bill_request.assert_not_called()

    @patch.object(BillingClient, "_request")
    @patch.object(MeteringClient, "_request")
    def test_record_usage_no_debit_when_billed_cost_is_none(self, mock_met_request, mock_bill_request):
        """When billing is enabled but billed_cost is None, no debit call."""
        mock_met_request.return_value = MagicMock(
            status_code=200, json=lambda: {
                "event_id": "evt_4", "new_balance_micros": 10_000_000,
                "suspended": False, "costing_status": "known", "pricing_status": "known",
            }
        )
        result = self.client.record_usage(
            customer_id="cust_1", idempotency_key="i4",
            provider_cost_micros=500_000,
        )
        self.assertEqual(result.event_id, "evt_4")
        mock_bill_request.assert_not_called()

    def test_record_usage_requires_metering(self):
        """record_usage raises UBBError when metering is not enabled."""
        from ubb.exceptions import UBBError
        client = UBBClient(api_key="ubb_test_key", metering=False, billing=True)
        with self.assertRaises(UBBError):
            client.record_usage(customer_id="c1", idempotency_key="i1", provider_cost_micros=1000)
        client.close()


class TestOrchestratedPreCheck(unittest.TestCase):
    """Test the orchestrated pre_check that delegates to billing."""

    def setUp(self):
        self.client = UBBClient(api_key="ubb_test_key", metering=True, billing=True)

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

    # ⚠ SIX CASES STOOD HERE AND ALL SIX WERE ABOUT THE RETIRED CREATION PATH
    # (#410). They proved that `start_task=True` threaded a unit of work's
    # fields onto the wire, that `UBBClient.start_task` was a wrapper around
    # that flag, that a named parent registered contained work, that a
    # registration refusal came back as a verdict, and that the method demanded
    # the billing product. Every one of those claims is about a call this
    # client can no longer make: the flag is gone from the contract, the
    # wrapper is deleted with it, and the route that registers work is
    # ungated, requires the caller's key, and answers a refusal as a refusal.
    #
    # THEY ARE DELETED RATHER THAN REPOINTED because #422 owns the SDK's start
    # and the shape of its signature, and a case rewritten here would be a
    # second answer to a question that ticket has to settle. What survives of
    # this client's half is the advisory check, covered by the cases above.

    def test_pre_check_no_billing_trivially_allowed(self):
        """Without billing, pre_check returns trivially allowed."""
        client = UBBClient(api_key="ubb_test_key", metering=True, billing=False)
        result = client.pre_check(customer_id="cust_1")
        self.assertTrue(result.allowed)
        self.assertTrue(result.can_proceed)
        self.assertIsNone(result.balance_micros)
        client.close()


# RETIRED (the wrap, #84): TestRecordUsageResultBalanceAfter pinned the hand
# RecordUsageResult's ``balance_after_micros`` field. That field is not in the
# committed RecordUsageResponse contract, so the generated model does not carry
# it — the DTO's shape is now owned by the spec + the CI regeneration gate, not
# a hand-written test. Nothing in the shell reads balance_after_micros.


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
