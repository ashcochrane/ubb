import pytest
from ubb.client import UBBClient


class TestUBBClientSubscriptions:
    def test_subscriptions_client_created_when_enabled(self):
        client = UBBClient(
            api_key="ubb_live_test",
            base_url="http://localhost:8001",
            max_retries=0,
            metering=True,
            subscriptions=True,
        )
        assert client.subscriptions is not None
        from ubb.subscriptions import SubscriptionsClient
        assert isinstance(client.subscriptions, SubscriptionsClient)
        client.close()

    def test_subscriptions_client_none_when_disabled(self):
        client = UBBClient(
            api_key="ubb_live_test",
            base_url="http://localhost:8001",
            max_retries=0,
            metering=True,
            subscriptions=False,
        )
        assert client.subscriptions is None
        client.close()

    def test_subscriptions_default_is_false(self):
        client = UBBClient(
            api_key="ubb_live_test",
            base_url="http://localhost:8001",
            max_retries=0,
        )
        assert client.subscriptions is None
        client.close()
