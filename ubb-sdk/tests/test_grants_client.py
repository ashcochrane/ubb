import unittest
from unittest.mock import patch, MagicMock

from ubb.billing import BillingClient
from ubb.types import BalanceResult, CreditGrant, PaginatedResponse


def _grant_body(**overrides):
    body = {
        "id": "g_1", "kind": "promo", "granted_micros": 10_000_000,
        "remaining_micros": 10_000_000, "expired_micros": 0, "voided_micros": 0,
        "currency": "USD", "status": "active", "source": "api",
        "expires_at": "2026-07-12T00:00:00+00:00", "warning_sent_at": None,
        "created_at": "2026-06-12T00:00:00+00:00",
        "balance_micros": 10_000_000, "transaction_id": "txn_1",
    }
    body.update(overrides)
    return body


class GrantsClientTest(unittest.TestCase):
    def setUp(self):
        self.client = BillingClient(api_key="ubb_live_test123",
                                    base_url="http://localhost:8001", max_retries=0)

    def tearDown(self):
        self.client.close()

    @patch("ubb.billing.httpx.Client.post")
    def test_create_grant(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: _grant_body())
        result = self.client.create_grant(
            customer_id="cust_1", kind="promo", amount_micros=10_000_000,
            idempotency_key="welcome-1", expires_in_days=30,
            description="Welcome bonus")
        self.assertIsInstance(result, CreditGrant)
        self.assertEqual(result.id, "g_1")
        self.assertEqual(result.remaining_micros, 10_000_000)
        self.assertEqual(result.status, "active")
        call_args = mock_post.call_args
        self.assertEqual(call_args.args[0], "/api/v1/billing/customers/cust_1/grants")
        body = call_args.kwargs["json"]
        self.assertEqual(body["kind"], "promo")
        self.assertEqual(body["amount_micros"], 10_000_000)
        self.assertEqual(body["idempotency_key"], "welcome-1")
        self.assertEqual(body["expires_in_days"], 30)
        self.assertEqual(body["description"], "Welcome bonus")
        self.assertNotIn("expires_at", body)

    @patch("ubb.billing.httpx.Client.post")
    def test_create_grant_with_expires_at(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: _grant_body())
        self.client.create_grant(
            customer_id="cust_1", kind="paid", amount_micros=5_000_000,
            idempotency_key="k2", expires_at="2026-07-12T00:00:00+00:00")
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["expires_at"], "2026-07-12T00:00:00+00:00")
        self.assertNotIn("expires_in_days", body)
        self.assertNotIn("description", body)

    @patch("ubb.billing.httpx.Client.get")
    def test_list_grants(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [_grant_body(balance_micros=None, transaction_id=None)],
            "next_cursor": None, "has_more": False,
        })
        result = self.client.list_grants(customer_id="cust_1", status="active")
        self.assertIsInstance(result, PaginatedResponse)
        self.assertEqual(len(result.data), 1)
        self.assertIsInstance(result.data[0], CreditGrant)
        self.assertFalse(result.has_more)
        call_args = mock_get.call_args
        self.assertEqual(call_args.args[0], "/api/v1/billing/customers/cust_1/grants")
        self.assertEqual(call_args.kwargs["params"]["status"], "active")

    @patch("ubb.billing.httpx.Client.post")
    def test_void_grant(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: _grant_body(
            status="voided", remaining_micros=0, voided_micros=10_000_000,
            balance_micros=0))
        result = self.client.void_grant(customer_id="cust_1", grant_id="g_1")
        self.assertEqual(result.status, "voided")
        self.assertEqual(result.voided_micros, 10_000_000)
        call_args = mock_post.call_args
        self.assertEqual(call_args.args[0],
                         "/api/v1/billing/customers/cust_1/grants/g_1/void")

    @patch("ubb.billing.httpx.Client.get")
    def test_get_balance_includes_grant_fields(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "balance_micros": 10_000_000, "currency": "USD",
            "promo_micros": 6_000_000, "expiring_micros": 10_000_000,
            "next_expiry_at": "2026-07-12T00:00:00+00:00",
        })
        result = self.client.get_balance(customer_id="cust_1")
        self.assertIsInstance(result, BalanceResult)
        self.assertEqual(result.promo_micros, 6_000_000)
        self.assertEqual(result.expiring_micros, 10_000_000)
        self.assertEqual(result.next_expiry_at, "2026-07-12T00:00:00+00:00")

    @patch("ubb.billing.httpx.Client.get")
    def test_get_balance_back_compat_without_grant_fields(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "balance_micros": 10_000_000, "currency": "USD",
        })
        result = self.client.get_balance(customer_id="cust_1")
        self.assertIsNone(result.promo_micros)
        self.assertIsNone(result.expiring_micros)
        self.assertIsNone(result.next_expiry_at)


if __name__ == "__main__":
    unittest.main()
