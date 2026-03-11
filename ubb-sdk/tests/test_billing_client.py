import unittest
from unittest.mock import patch, MagicMock
import httpx
from ubb.billing import BillingClient
from ubb.exceptions import (
    UBBAuthError, UBBAPIError, UBBConflictError, UBBConnectionError,
)
from ubb.types import BalanceResult, TopUpResult, WalletTransaction, PaginatedResponse


class BillingClientTest(unittest.TestCase):
    def setUp(self):
        self.client = BillingClient(api_key="ubb_live_test123", base_url="http://localhost:8001", max_retries=0)

    def tearDown(self):
        self.client.close()

    # ---- debit ----

    @patch("ubb.billing.httpx.Client.post")
    def test_debit(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "transaction_id": "txn_1", "balance_after_micros": 8_500_000,
        })
        result = self.client.debit(
            customer_id="cust_1", amount_micros=1_500_000, reference="evt_1",
        )
        self.assertEqual(result["transaction_id"], "txn_1")
        self.assertEqual(result["balance_after_micros"], 8_500_000)
        call_args = mock_post.call_args
        self.assertEqual(call_args.args[0], "/api/v1/billing/debit")

    # ---- credit ----

    @patch("ubb.billing.httpx.Client.post")
    def test_credit(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "transaction_id": "txn_2", "balance_after_micros": 11_500_000,
        })
        result = self.client.credit(
            customer_id="cust_1", amount_micros=1_500_000,
            source="top_up", reference="topup_1",
        )
        self.assertEqual(result["transaction_id"], "txn_2")
        call_args = mock_post.call_args
        self.assertEqual(call_args.args[0], "/api/v1/billing/credit")

    # ---- get_balance ----

    @patch("ubb.billing.httpx.Client.get")
    def test_get_balance(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "balance_micros": 10_000_000, "currency": "USD",
        })
        result = self.client.get_balance(customer_id="cust_1")
        self.assertIsInstance(result, BalanceResult)
        self.assertEqual(result.balance_micros, 10_000_000)
        self.assertEqual(result.currency, "USD")
        call_args = mock_get.call_args
        self.assertEqual(call_args.args[0], "/api/v1/billing/customers/cust_1/balance")

    # ---- pre_check ----

    @patch("ubb.billing.httpx.Client.post")
    def test_pre_check(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "allowed": True, "reason": None, "balance_micros": 10_000_000,
        })
        result = self.client.pre_check(customer_id="cust_1")
        self.assertTrue(result["allowed"])
        call_args = mock_post.call_args
        self.assertEqual(call_args.args[0], "/api/v1/billing/pre-check")
        body = call_args.kwargs["json"]
        self.assertEqual(body["customer_id"], "cust_1")
        self.assertNotIn("estimated_cost", body)

    @patch("ubb.billing.httpx.Client.post")
    def test_pre_check_denied(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "allowed": False, "reason": "insufficient_funds", "balance_micros": -6_000_000,
        })
        result = self.client.pre_check(customer_id="cust_1")
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "insufficient_funds")

    # ---- create_top_up ----

    @patch("ubb.billing.httpx.Client.post")
    def test_create_top_up(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "checkout_url": "https://checkout.stripe.com/abc",
        })
        result = self.client.create_top_up(
            customer_id="cust_1", amount_micros=50_000_000,
            success_url="https://app.example.com/success",
            cancel_url="https://app.example.com/cancel",
        )
        self.assertIsInstance(result, TopUpResult)
        self.assertEqual(result.checkout_url, "https://checkout.stripe.com/abc")
        call_args = mock_post.call_args
        self.assertEqual(call_args.args[0], "/api/v1/billing/customers/cust_1/top-up")

    # ---- configure_auto_topup ----

    @patch("ubb.billing.httpx.Client.put")
    def test_configure_auto_topup(self, mock_put):
        mock_put.return_value = MagicMock(status_code=200, json=lambda: {"status": "ok"})
        result = self.client.configure_auto_topup(
            customer_id="cust_1", is_enabled=True,
            trigger_threshold_micros=5_000_000, top_up_amount_micros=50_000_000,
        )
        self.assertEqual(result["status"], "ok")
        call_args = mock_put.call_args
        self.assertEqual(call_args.args[0], "/api/v1/billing/customers/cust_1/auto-top-up")
        body = call_args.kwargs["json"]
        self.assertTrue(body["is_enabled"])
        self.assertEqual(body["trigger_threshold_micros"], 5_000_000)

    @patch("ubb.billing.httpx.Client.put")
    def test_configure_auto_topup_disable(self, mock_put):
        mock_put.return_value = MagicMock(status_code=200, json=lambda: {"status": "ok"})
        result = self.client.configure_auto_topup(
            customer_id="cust_1", is_enabled=False,
        )
        self.assertEqual(result["status"], "ok")
        body = mock_put.call_args.kwargs["json"]
        self.assertFalse(body["is_enabled"])
        self.assertNotIn("trigger_threshold_micros", body)

    # ---- get_transactions ----

    @patch("ubb.billing.httpx.Client.get")
    def test_get_transactions(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [
                {
                    "id": "t1", "transaction_type": "DEBIT", "amount_micros": -100000,
                    "balance_after_micros": 9_900_000, "description": "Usage debit",
                    "reference_id": "evt_1", "created_at": "2025-01-01T00:00:00Z",
                },
            ],
            "next_cursor": None,
            "has_more": False,
        })
        result = self.client.get_transactions(customer_id="cust_1")
        self.assertIsInstance(result, PaginatedResponse)
        self.assertEqual(len(result.data), 1)
        self.assertIsInstance(result.data[0], WalletTransaction)
        self.assertFalse(result.has_more)
        call_args = mock_get.call_args
        self.assertEqual(call_args.args[0], "/api/v1/billing/customers/cust_1/transactions")

    @patch("ubb.billing.httpx.Client.get")
    def test_get_transactions_with_cursor(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [], "next_cursor": None, "has_more": False,
        })
        self.client.get_transactions(customer_id="cust_1", cursor="cur_abc", limit=10)
        call_kwargs = mock_get.call_args
        self.assertEqual(call_kwargs.kwargs["params"]["cursor"], "cur_abc")
        self.assertEqual(call_kwargs.kwargs["params"]["limit"], 10)

    # ---- error handling ----

    @patch("ubb.billing.httpx.Client.post")
    def test_auth_error_raises(self, mock_post):
        mock_post.return_value = MagicMock(status_code=401)
        with self.assertRaises(UBBAuthError):
            self.client.debit(customer_id="c1", amount_micros=1000, reference="ref")

    @patch("ubb.billing.httpx.Client.get")
    def test_api_error_raises(self, mock_get):
        mock_get.return_value = MagicMock(status_code=500, text="Internal Server Error")
        mock_get.return_value.json.side_effect = Exception("not json")
        with self.assertRaises(UBBAPIError):
            self.client.get_balance(customer_id="c1")

    @patch("ubb.billing.httpx.Client.post")
    def test_403_product_access_denied(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=403, text="Forbidden",
            json=lambda: {"detail": "Product 'billing' not enabled for this tenant"},
        )
        with self.assertRaises(UBBAPIError) as ctx:
            self.client.debit(customer_id="c1", amount_micros=1000, reference="ref")
        self.assertEqual(ctx.exception.status_code, 403)

    @patch("ubb.billing.httpx.Client.post")
    def test_timeout_raises_connection_error(self, mock_post):
        mock_post.side_effect = httpx.TimeoutException("timed out")
        with self.assertRaises(UBBConnectionError) as ctx:
            self.client.debit(customer_id="c1", amount_micros=1000, reference="ref")
        self.assertIsNotNone(ctx.exception.original)

    @patch("ubb.billing.httpx.Client.post")
    def test_connect_error_raises_connection_error(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("connection refused")
        with self.assertRaises(UBBConnectionError) as ctx:
            self.client.debit(customer_id="c1", amount_micros=1000, reference="ref")
        self.assertIn("Could not connect", str(ctx.exception))

    # ---- context manager ----

    def test_context_manager(self):
        with patch.object(self.client, "close") as mock_close:
            with self.client:
                pass
            mock_close.assert_called_once()

    # ---- close ----

    def test_close(self):
        with patch.object(self.client._http, "close") as mock_close:
            self.client.close()
            mock_close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
