"""Tests for UBBClient delegation to product clients.

Verifies that:
1. UBBClient no longer has its own _http client
2. Billing methods raise UBBError when billing product is not enabled
3. Metering methods raise UBBError when metering product is not enabled
4. Methods properly delegate to the appropriate product client
5. create_customer uses metering's _request for the platform API
"""
import pytest
from unittest.mock import MagicMock, patch

from ubb import UBBClient, SubscriptionsClient
from ubb.exceptions import UBBError
from ubb.types import BalanceResult, TopUpResult, PaginatedResponse, WalletTransaction


class TestLegacyHTTPRemoved:
    """Verify the legacy _http client and related methods are removed."""

    def test_no_http_client(self):
        client = UBBClient(api_key="test", max_retries=0)
        assert not hasattr(client, "_http")
        client.close()

    def test_no_request_method(self):
        client = UBBClient(api_key="test", max_retries=0)
        assert not hasattr(client, "_request")
        client.close()

    def test_no_extract_error_detail(self):
        client = UBBClient(api_key="test", max_retries=0)
        assert not hasattr(client, "_extract_error_detail")
        client.close()

    def test_no_billing_client_alias(self):
        client = UBBClient(api_key="test", max_retries=0, billing=True)
        assert not hasattr(client, "billing_client")
        client.close()


class TestBillingDelegationRequiresBilling:
    """Methods that require billing raise UBBError when billing is disabled."""

    def setup_method(self):
        self.client = UBBClient(api_key="test", max_retries=0, metering=True, billing=False)

    def teardown_method(self):
        self.client.close()

    def test_get_balance_requires_billing(self):
        with pytest.raises(UBBError, match="billing"):
            self.client.get_balance("cust1")

    def test_create_top_up_requires_billing(self):
        with pytest.raises(UBBError, match="billing"):
            self.client.create_top_up("cust1", 100_000,
                                      success_url="http://ok", cancel_url="http://no")

    def test_configure_auto_top_up_requires_billing(self):
        with pytest.raises(UBBError, match="billing"):
            self.client.configure_auto_top_up("cust1", threshold=0, amount=100_000)

    def test_withdraw_requires_billing(self):
        with pytest.raises(UBBError, match="billing"):
            self.client.withdraw("cust1", 100_000, "w1")

    def test_refund_usage_requires_billing(self):
        with pytest.raises(UBBError, match="billing"):
            self.client.refund_usage("cust1", "evt1", "r1")

    def test_get_transactions_requires_billing(self):
        with pytest.raises(UBBError, match="billing"):
            self.client.get_transactions("cust1")


class TestMeteringDelegationRequiresMetering:
    """Methods that require metering raise UBBError when metering is disabled."""

    def setup_method(self):
        self.client = UBBClient(api_key="test", max_retries=0, metering=False, billing=True)

    def teardown_method(self):
        self.client.close()

    def test_record_usage_requires_metering(self):
        with pytest.raises(UBBError, match="metering"):
            self.client.record_usage("cust1", "r1", "i1")

    def test_pre_check_without_metering_delegates_to_billing(self):
        """pre_check no longer requires metering — delegates to billing if available."""
        self.client.billing.pre_check = MagicMock(return_value={
            "allowed": True, "can_proceed": True, "balance_micros": 5_000_000,
        })
        result = self.client.pre_check("cust1")
        assert result.allowed is True
        self.client.billing.pre_check.assert_called_once_with(
            "cust1", start_run=False, run_metadata=None, external_run_id="",
        )

    def test_get_usage_requires_metering(self):
        with pytest.raises(UBBError, match="metering"):
            self.client.get_usage("cust1")

    def test_create_customer_requires_metering(self):
        with pytest.raises(UBBError, match="metering"):
            self.client.create_customer("ext1")


class TestBillingDelegation:
    """Methods properly delegate to the billing product client."""

    def setup_method(self):
        self.client = UBBClient(api_key="test", max_retries=0, metering=True, billing=True)

    def teardown_method(self):
        self.client.close()

    def test_get_balance_delegates(self):
        expected = BalanceResult(balance_micros=5_000_000, currency="USD")
        self.client.billing.get_balance = MagicMock(return_value=expected)
        result = self.client.get_balance("cust1")
        self.client.billing.get_balance.assert_called_once_with("cust1")
        assert result is expected

    def test_create_top_up_delegates(self):
        expected = TopUpResult(checkout_url="https://example.com/checkout")
        self.client.billing.create_top_up = MagicMock(return_value=expected)
        result = self.client.create_top_up("cust1", 100_000,
                                           success_url="http://ok",
                                           cancel_url="http://no")
        self.client.billing.create_top_up.assert_called_once_with(
            "cust1", 100_000, "http://ok", "http://no",
        )
        assert result is expected

    def test_get_transactions_delegates(self):
        expected = PaginatedResponse(data=[], next_cursor=None, has_more=False)
        self.client.billing.get_transactions = MagicMock(return_value=expected)
        result = self.client.get_transactions("cust1", limit=10)
        self.client.billing.get_transactions.assert_called_once_with(
            "cust1", cursor=None, limit=10,
        )
        assert result is expected


class TestMeteringDelegation:
    """Methods properly delegate to the metering product client."""

    def setup_method(self):
        self.client = UBBClient(api_key="test", max_retries=0, metering=True, billing=False)

    def teardown_method(self):
        self.client.close()

    def test_get_usage_delegates(self):
        expected = PaginatedResponse(data=[], next_cursor=None, has_more=False)
        self.client.metering.get_usage = MagicMock(return_value=expected)
        result = self.client.get_usage("cust1", limit=25)
        self.client.metering.get_usage.assert_called_once_with(
            "cust1", cursor=None, limit=25,
        )
        assert result is expected


class TestCreateCustomerDelegation:
    """create_customer uses metering._request to call the platform API."""

    def test_create_customer_uses_metering_request(self):
        client = UBBClient(api_key="test", max_retries=0, metering=True)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "c1", "external_id": "ext1", "status": "active",
        }
        client.metering._request = MagicMock(return_value=mock_response)

        result = client.create_customer("ext1", stripe_customer_id="cus_123")

        client.metering._request.assert_called_once_with(
            "post", "/api/v1/platform/customers", json={
                "external_id": "ext1",
                "stripe_customer_id": "cus_123",
                "metadata": {},
            }
        )
        assert result.external_id == "ext1"
        assert result.id == "c1"
        client.close()


class TestSubscriptionsExport:
    """SubscriptionsClient is exported from ubb package."""

    def test_subscriptions_client_importable(self):
        from ubb import SubscriptionsClient
        assert SubscriptionsClient is not None

    def test_subscriptions_client_in_all(self):
        import ubb
        assert "SubscriptionsClient" in ubb.__all__


class TestCloseNoHTTP:
    """close() does not reference _http."""

    def test_close_only_closes_product_clients(self):
        client = UBBClient(api_key="test", max_retries=0, metering=True, billing=True,
                           subscriptions=True, referrals=True)
        with patch.object(client.metering, "close") as m_close, \
             patch.object(client.billing, "close") as b_close, \
             patch.object(client.subscriptions, "close") as s_close, \
             patch.object(client.referrals, "close") as r_close:
            client.close()
            m_close.assert_called_once()
            b_close.assert_called_once()
            s_close.assert_called_once()
            r_close.assert_called_once()

    def test_close_with_none_clients_does_not_error(self):
        client = UBBClient(api_key="test", max_retries=0, metering=False, billing=False)
        client.close()  # Should not raise


class TestPreCheckWithoutEventType:
    """pre_check without event_type should work with the new delegation model."""

    def test_pre_check_metering_only_no_event_type(self):
        """With metering only, no event_type: trivially allowed."""
        client = UBBClient(api_key="test", max_retries=0, metering=True, billing=False)
        result = client.pre_check(customer_id="cust1")
        assert result.allowed is True
        assert result.can_proceed is True
        client.close()

    def test_pre_check_with_billing_delegates(self):
        """With billing enabled, delegates to billing.pre_check."""
        client = UBBClient(api_key="test", max_retries=0, metering=True, billing=True)
        client.billing.pre_check = MagicMock(return_value={
            "allowed": True, "can_proceed": True, "balance_micros": 5_000_000,
        })
        result = client.pre_check(customer_id="cust1")
        client.billing.pre_check.assert_called_once_with(
            "cust1", start_run=False, run_metadata=None, external_run_id="",
        )
        assert result.allowed is True
        assert result.balance_micros == 5_000_000
        client.close()
