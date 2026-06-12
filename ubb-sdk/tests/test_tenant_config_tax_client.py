import unittest
from unittest.mock import MagicMock

from ubb.client import UBBClient

CONFIG_FIXTURE = {
    "name": "TestTenant",
    "billing_mode": "meter_only",
    "products": ["metering"],
    "require_cost_card_coverage": False,
    "default_currency": "usd",
    "stripe_connected_account_id": "acct_test",
    "is_active": True,
    "automatic_tax_enabled": True,
}


class TenantConfigAutomaticTaxTest(unittest.TestCase):
    """update_tenant_config passes the F5.3 automatic_tax_enabled kwarg through."""

    def setUp(self):
        self.client = UBBClient(api_key="ubb_live_test", metering=True)

    def tearDown(self):
        self.client.close()

    def test_update_tenant_config_sends_automatic_tax_enabled(self):
        mock_resp = MagicMock(status_code=200, json=lambda: CONFIG_FIXTURE)
        self.client.metering._request = MagicMock(return_value=mock_resp)
        result = self.client.update_tenant_config(automatic_tax_enabled=True)
        self.client.metering._request.assert_called_once_with(
            "patch", "/api/v1/tenant/config",
            json={"automatic_tax_enabled": True},
        )
        self.assertTrue(result["automatic_tax_enabled"])

    def test_update_tenant_config_omits_flag_when_not_given(self):
        mock_resp = MagicMock(status_code=200, json=lambda: CONFIG_FIXTURE)
        self.client.metering._request = MagicMock(return_value=mock_resp)
        self.client.update_tenant_config(billing_mode="postpaid")
        self.client.metering._request.assert_called_once_with(
            "patch", "/api/v1/tenant/config",
            json={"billing_mode": "postpaid"},
        )

    def test_explicit_false_is_sent(self):
        mock_resp = MagicMock(status_code=200, json=lambda: CONFIG_FIXTURE)
        self.client.metering._request = MagicMock(return_value=mock_resp)
        self.client.update_tenant_config(automatic_tax_enabled=False)
        self.client.metering._request.assert_called_once_with(
            "patch", "/api/v1/tenant/config",
            json={"automatic_tax_enabled": False},
        )


if __name__ == "__main__":
    unittest.main()
