import httpx
from unittest.mock import patch
from ubb.referrals import ReferralsClient


class TestReferralsClient:
    def test_create_program(self):
        client = ReferralsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "post") as mock_post:
            mock_post.return_value = httpx.Response(200, json={
                "id": "prog-1",
                "reward_type": "revenue_share",
                "reward_value": 0.10,
                "attribution_window_days": 30,
                "reward_window_days": 365,
                "max_reward_micros": None,
                "estimated_cost_percentage": None,
                "status": "active",
                "created_at": "2026-02-06T00:00:00Z",
                "updated_at": "2026-02-06T00:00:00Z",
            })

            result = client.create_program("revenue_share", 0.10, reward_window_days=365)
            call_url = mock_post.call_args[0][0]
            assert "/referrals/program" in call_url
            assert result["reward_type"] == "revenue_share"

    def test_get_program(self):
        client = ReferralsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "get") as mock_get:
            mock_get.return_value = httpx.Response(200, json={
                "id": "prog-1",
                "reward_type": "flat_fee",
                "reward_value": 5000000,
                "status": "active",
            })

            result = client.get_program()
            call_url = mock_get.call_args[0][0]
            assert "/referrals/program" in call_url
            assert result["status"] == "active"

    def test_update_program(self):
        client = ReferralsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "patch") as mock_patch:
            mock_patch.return_value = httpx.Response(200, json={
                "id": "prog-1",
                "reward_value": 0.20,
                "status": "active",
            })

            result = client.update_program(reward_value=0.20)
            assert result["reward_value"] == 0.20

    def test_deactivate_program(self):
        client = ReferralsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "delete") as mock_del:
            mock_del.return_value = httpx.Response(200, json={"status": "deactivated"})

            result = client.deactivate_program()
            assert result["status"] == "deactivated"

    def test_reactivate_program(self):
        client = ReferralsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "post") as mock_post:
            mock_post.return_value = httpx.Response(200, json={"status": "active"})

            result = client.reactivate_program()
            assert result["status"] == "active"

    def test_register_referrer(self):
        client = ReferralsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "post") as mock_post:
            mock_post.return_value = httpx.Response(200, json={
                "id": "ref-1",
                "customer_id": "cust-1",
                "referral_code": "REF-ABCDEFGH",
                "referral_link_token": "token123",
                "is_active": True,
                "created_at": "2026-02-06T00:00:00Z",
            })

            result = client.register_referrer("cust-1")
            assert result["referral_code"].startswith("REF-")

    def test_get_referrer(self):
        client = ReferralsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "get") as mock_get:
            mock_get.return_value = httpx.Response(200, json={
                "id": "ref-1",
                "customer_id": "cust-1",
                "referral_code": "REF-ABCDEFGH",
                "is_active": True,
            })

            result = client.get_referrer("cust-1")
            assert result["customer_id"] == "cust-1"

    def test_list_referrers(self):
        client = ReferralsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "get") as mock_get:
            mock_get.return_value = httpx.Response(200, json={
                "data": [{"id": "ref-1"}],
                "next_cursor": None,
                "has_more": False,
            })

            result = client.list_referrers()
            assert len(result["data"]) == 1

    def test_attribute_with_code(self):
        client = ReferralsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "post") as mock_post:
            mock_post.return_value = httpx.Response(200, json={
                "referral_id": "referral-1",
                "referrer_id": "ref-1",
                "referred_customer_id": "cust-2",
                "status": "active",
            })

            result = client.attribute("cust-2", code="REF-ABCDEFGH")
            assert result["status"] == "active"

    def test_attribute_with_link_token(self):
        client = ReferralsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "post") as mock_post:
            mock_post.return_value = httpx.Response(200, json={
                "referral_id": "referral-1",
                "status": "active",
            })

            result = client.attribute("cust-2", link_token="token123")
            assert result["status"] == "active"

    def test_get_earnings(self):
        client = ReferralsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "get") as mock_get:
            mock_get.return_value = httpx.Response(200, json={
                "referrer_customer_id": "cust-1",
                "total_earned_micros": 500_000,
                "total_referred_spend_micros": 5_000_000,
                "total_referrals": 3,
                "active_referrals": 2,
            })

            result = client.get_earnings("cust-1")
            assert result["total_earned_micros"] == 500_000

    def test_get_referrals(self):
        client = ReferralsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "get") as mock_get:
            mock_get.return_value = httpx.Response(200, json={
                "data": [{"id": "ref-1", "status": "active"}],
                "next_cursor": None,
                "has_more": False,
            })

            result = client.get_referrals("cust-1")
            assert len(result["data"]) == 1

    def test_get_ledger(self):
        client = ReferralsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "get") as mock_get:
            mock_get.return_value = httpx.Response(200, json={
                "data": [],
                "next_cursor": None,
                "has_more": False,
            })

            result = client.get_ledger("referral-1")
            assert result["has_more"] is False

    def test_revoke_referral(self):
        client = ReferralsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "delete") as mock_del:
            mock_del.return_value = httpx.Response(200, json={"status": "revoked"})

            result = client.revoke_referral("referral-1")
            assert result["status"] == "revoked"

    def test_get_analytics_summary(self):
        client = ReferralsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "get") as mock_get:
            mock_get.return_value = httpx.Response(200, json={
                "total_referrers": 5,
                "total_referrals": 20,
                "active_referrals": 15,
                "total_rewards_earned_micros": 1_000_000,
                "total_referred_spend_micros": 10_000_000,
            })

            result = client.get_analytics_summary()
            assert result["total_referrers"] == 5

    def test_get_analytics_earnings(self):
        client = ReferralsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "get") as mock_get:
            mock_get.return_value = httpx.Response(200, json={
                "period_start": "2026-02-01",
                "period_end": "2026-02-06",
                "referrers": [],
                "total_earned_micros": 0,
            })

            result = client.get_analytics_earnings()
            assert result["referrers"] == []
