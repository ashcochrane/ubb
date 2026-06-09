import unittest
from unittest.mock import patch, MagicMock
from ubb.metering import MeteringClient
from ubb.client import UBBClient
from ubb.types import CustomerResult


CUSTOMER_FIXTURE = {
    "id": "biz1", "external_id": "biz", "status": "active",
}

BUSINESS_FIXTURE = {
    "id": "biz1",
    "external_id": "biz",
    "account_type": "business",
    "billing_topology": "pooled",
    "status": "active",
    "members": [],
}


class AccountsClientTest(unittest.TestCase):
    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_t", base_url="http://localhost:8001")

    def tearDown(self):
        self.client.close()

    @patch("ubb.metering.httpx.Client.post")
    def test_create_customer_with_account_type_and_billing_topology(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: CUSTOMER_FIXTURE)
        ubb = UBBClient(api_key="ubb_live_t", metering=True)
        ubb.metering._http = self.client._http

        # Replace the underlying HTTP client's post method on the actual metering client
        ubb.metering._request = MagicMock(
            return_value=MagicMock(status_code=200, json=lambda: CUSTOMER_FIXTURE)
        )

        result = ubb.create_customer(
            external_id="biz",
            account_type="business",
            billing_topology="pooled",
        )

        ubb.metering._request.assert_called_once_with(
            "post", "/api/v1/customers", json={
                "external_id": "biz",
                "stripe_customer_id": "",
                "metadata": {},
                "account_type": "business",
                "parent_external_id": "",
                "billing_topology": "pooled",
            }
        )
        self.assertIsInstance(result, CustomerResult)
        self.assertEqual(result.external_id, "biz")
        ubb.close()

    @patch("ubb.metering.httpx.Client.get")
    def test_get_business_hits_correct_url(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: BUSINESS_FIXTURE)
        result = self.client._request("get", "/api/v1/accounts/business/biz")
        self.assertEqual(mock_get.call_args.args[0], "/api/v1/accounts/business/biz")
        self.assertEqual(result.json(), BUSINESS_FIXTURE)

    @patch("ubb.metering.httpx.Client.get")
    def test_get_business_returns_dict(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: BUSINESS_FIXTURE)
        ubb = UBBClient(api_key="ubb_live_t", metering=True)
        ubb.metering._request = MagicMock(
            return_value=MagicMock(status_code=200, json=lambda: BUSINESS_FIXTURE)
        )

        result = ubb.get_business("biz")

        ubb.metering._request.assert_called_once_with(
            "get", "/api/v1/accounts/business/biz"
        )
        self.assertIsInstance(result, dict)
        self.assertEqual(result["external_id"], "biz")
        self.assertEqual(result["account_type"], "business")
        self.assertEqual(result["billing_topology"], "pooled")
        ubb.close()


if __name__ == "__main__":
    unittest.main()
