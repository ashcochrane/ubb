import unittest
from unittest.mock import patch, MagicMock
import httpx
from ubb.client import UBBClient, _check_micros, _check_micros_allow_zero
from ubb.exceptions import (
    UBBAuthError, UBBAPIError, UBBConflictError, UBBValidationError, UBBConnectionError,
)
from ubb.types import (
    PreCheckResult, RecordUsageResult, CustomerResult, BalanceResult,
    UsageEvent, TopUpResult, AutoTopUpResult, WithdrawResult, RefundResult,
    WalletTransaction, PaginatedResponse,
)


class UBBClientTest(unittest.TestCase):
    def setUp(self):
        self.client = UBBClient(api_key="ubb_live_test123", base_url="http://localhost:8001")

    # --- Existing tests (updated) ---

    @patch("ubb.client.httpx.Client.post")
    def test_pre_check(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"allowed": True, "reason": None})
        result = self.client.pre_check(customer_id="cust_123")
        self.assertTrue(result.allowed)
        self.assertIsNone(result.reason)

    @patch("ubb.client.httpx.Client.post")
    def test_record_usage(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_1", "new_balance_micros": 8500000, "suspended": False,
        })
        result = self.client.record_usage(
            customer_id="c1", request_id="r1", idempotency_key="i1", cost_micros=1500000,
        )
        self.assertEqual(result.new_balance_micros, 8500000)
        self.assertFalse(result.suspended)

    @patch("ubb.client.httpx.Client.post")
    def test_create_customer(self, mock_post):
        mock_post.return_value = MagicMock(status_code=201, json=lambda: {
            "id": "c1", "external_id": "u42", "email": "j@example.com", "status": "active",
        })
        result = self.client.create_customer(external_id="u42", email="j@example.com")
        self.assertEqual(result.external_id, "u42")

    @patch("ubb.client.httpx.Client.get")
    def test_get_balance(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "balance_micros": 10000000, "currency": "USD",
        })
        result = self.client.get_balance(customer_id="c1")
        self.assertEqual(result.balance_micros, 10000000)

    @patch("ubb.client.httpx.Client.post")
    def test_auth_error_raises(self, mock_post):
        mock_post.return_value = MagicMock(status_code=401)
        with self.assertRaises(UBBAuthError):
            self.client.pre_check(customer_id="c1")

    @patch("ubb.client.httpx.Client.post")
    def test_api_error_raises(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500, text="Internal Server Error")
        mock_post.return_value.json.side_effect = Exception("not json")
        with self.assertRaises(UBBAPIError):
            self.client.pre_check(customer_id="c1")

    # --- Context manager ---

    def test_context_manager(self):
        with patch.object(self.client, "close") as mock_close:
            with self.client:
                pass
            mock_close.assert_called_once()

    # --- Connection errors ---

    @patch("ubb.client.httpx.Client.post")
    def test_timeout_raises_connection_error(self, mock_post):
        mock_post.side_effect = httpx.TimeoutException("timed out")
        with self.assertRaises(UBBConnectionError) as ctx:
            self.client.pre_check(customer_id="c1")
        self.assertIsNotNone(ctx.exception.original)

    @patch("ubb.client.httpx.Client.post")
    def test_connect_error_raises_connection_error(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("connection refused")
        with self.assertRaises(UBBConnectionError) as ctx:
            self.client.pre_check(customer_id="c1")
        self.assertIn("Could not connect", str(ctx.exception))

    # --- 409 Conflict ---

    @patch("ubb.client.httpx.Client.post")
    def test_conflict_raises(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=409, text="Conflict",
            json=lambda: {"error": "duplicate external_id"},
        )
        with self.assertRaises(UBBConflictError) as ctx:
            self.client.create_customer(external_id="dup", email="a@b.com")
        self.assertEqual(ctx.exception.status_code, 409)

    # --- Client-side validation ---

    def test_check_micros_rejects_zero(self):
        with self.assertRaises(UBBValidationError):
            _check_micros(0, "cost_micros")

    def test_check_micros_rejects_negative(self):
        with self.assertRaises(UBBValidationError):
            _check_micros(-10_000, "cost_micros")

    def test_record_usage_validates_cost_micros(self):
        with self.assertRaises(UBBValidationError):
            self.client.record_usage(
                customer_id="c1", request_id="r1", idempotency_key="i1", cost_micros=1234,
            )

    def test_create_top_up_validates_amount_micros(self):
        with self.assertRaises(UBBValidationError):
            self.client.create_top_up(customer_id="c1", amount_micros=999)

    def test_configure_auto_top_up_validates_amount(self):
        with self.assertRaises(UBBValidationError):
            self.client.configure_auto_top_up(customer_id="c1", threshold=0, amount=1234)

    def test_configure_auto_top_up_validates_threshold(self):
        with self.assertRaises(UBBValidationError):
            self.client.configure_auto_top_up(customer_id="c1", threshold=1234, amount=10_000)

    def test_withdraw_validates_amount_micros(self):
        with self.assertRaises(UBBValidationError):
            self.client.withdraw(customer_id="c1", amount_micros=5555, idempotency_key="w1")

    # --- New method: get_usage (paginated) ---

    @patch("ubb.client.httpx.Client.get")
    def test_get_usage(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [
                {"id": "e1", "request_id": "r1", "cost_micros": 10000, "metadata": {}, "effective_at": "2025-01-01T00:00:00Z"},
            ],
            "next_cursor": "cur_abc",
            "has_more": True,
        })
        result = self.client.get_usage(customer_id="c1")
        self.assertIsInstance(result, PaginatedResponse)
        self.assertEqual(len(result.data), 1)
        self.assertIsInstance(result.data[0], UsageEvent)
        self.assertTrue(result.has_more)
        self.assertEqual(result.next_cursor, "cur_abc")

    @patch("ubb.client.httpx.Client.get")
    def test_get_usage_with_cursor(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [], "next_cursor": None, "has_more": False,
        })
        self.client.get_usage(customer_id="c1", cursor="cur_abc", limit=10)
        call_kwargs = mock_get.call_args
        self.assertIn("params", call_kwargs.kwargs)
        self.assertEqual(call_kwargs.kwargs["params"]["cursor"], "cur_abc")
        self.assertEqual(call_kwargs.kwargs["params"]["limit"], 10)

    # --- New method: create_top_up (typed) ---

    @patch("ubb.client.httpx.Client.post")
    def test_create_top_up(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "checkout_url": "https://checkout.example.com/abc",
        })
        result = self.client.create_top_up(customer_id="c1", amount_micros=50_000)
        self.assertIsInstance(result, TopUpResult)
        self.assertEqual(result.checkout_url, "https://checkout.example.com/abc")

    # --- New method: configure_auto_top_up (typed) ---

    @patch("ubb.client.httpx.Client.put")
    def test_configure_auto_top_up(self, mock_put):
        mock_put.return_value = MagicMock(status_code=200, json=lambda: {"status": "enabled"})
        result = self.client.configure_auto_top_up(customer_id="c1", threshold=0, amount=100_000)
        self.assertIsInstance(result, AutoTopUpResult)
        self.assertEqual(result.status, "enabled")

    # --- New method: withdraw ---

    @patch("ubb.client.httpx.Client.post")
    def test_withdraw(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "transaction_id": "txn_1", "balance_micros": 5000000,
        })
        result = self.client.withdraw(customer_id="c1", amount_micros=10_000, idempotency_key="w1")
        self.assertIsInstance(result, WithdrawResult)
        self.assertEqual(result.transaction_id, "txn_1")
        self.assertEqual(result.balance_micros, 5000000)

    # --- New method: refund_usage ---

    @patch("ubb.client.httpx.Client.post")
    def test_refund_usage(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "refund_id": "ref_1", "balance_micros": 11000000,
        })
        result = self.client.refund_usage(
            customer_id="c1", usage_event_id="evt_1", idempotency_key="rf1", reason="mistake",
        )
        self.assertIsInstance(result, RefundResult)
        self.assertEqual(result.refund_id, "ref_1")

    # --- New method: get_transactions ---

    @patch("ubb.client.httpx.Client.get")
    def test_get_transactions(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [
                {
                    "id": "t1", "transaction_type": "top_up", "amount_micros": 100000,
                    "balance_after_micros": 200000, "description": "Top up",
                    "reference_id": "ref_1", "created_at": "2025-01-01T00:00:00Z",
                },
            ],
            "next_cursor": None,
            "has_more": False,
        })
        result = self.client.get_transactions(customer_id="c1")
        self.assertIsInstance(result, PaginatedResponse)
        self.assertEqual(len(result.data), 1)
        self.assertIsInstance(result.data[0], WalletTransaction)
        self.assertFalse(result.has_more)

    # --- close ---

    def test_close(self):
        with patch.object(self.client._http, "close") as mock_close:
            self.client.close()
            mock_close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
