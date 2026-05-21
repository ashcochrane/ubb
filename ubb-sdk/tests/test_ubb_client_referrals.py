from ubb.client import UBBClient


class TestUBBClientReferrals:
    def test_referrals_client_created_when_enabled(self):
        client = UBBClient(
            api_key="ubb_live_test",
            base_url="http://localhost:8001",
            max_retries=0,
            metering=True,
            referrals=True,
        )
        assert client.referrals is not None
        from ubb.referrals import ReferralsClient
        assert isinstance(client.referrals, ReferralsClient)
        client.close()

    def test_referrals_client_none_when_disabled(self):
        client = UBBClient(
            api_key="ubb_live_test",
            base_url="http://localhost:8001",
            max_retries=0,
            metering=True,
            referrals=False,
        )
        assert client.referrals is None
        client.close()

    def test_referrals_default_is_false(self):
        client = UBBClient(
            api_key="ubb_live_test",
            base_url="http://localhost:8001",
            max_retries=0,
        )
        assert client.referrals is None
        client.close()
