import pytest
import httpx
from unittest.mock import patch
from ubb.subscriptions import SubscriptionsClient


class TestSubscriptionsClient:
    def test_sync_calls_subscriptions_endpoint(self):
        client = SubscriptionsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "post") as mock_post:
            mock_post.return_value = httpx.Response(
                200, json={"synced": 5, "skipped": 1, "errors": 0},
            )
            result = client.sync()

            call_url = mock_post.call_args[0][0]
            assert "/subscriptions/sync" in call_url
            assert result["synced"] == 5

    def test_get_economics_calls_subscriptions_endpoint(self):
        client = SubscriptionsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "get") as mock_get:
            mock_get.return_value = httpx.Response(200, json={
                "period": {"start": "2026-01-01", "end": "2026-02-01"},
                "customers": [],
                "summary": {
                    "total_revenue_micros": 0,
                    "total_cost_micros": 0,
                    "total_margin_micros": 0,
                    "avg_margin_percentage": 0,
                    "unprofitable_customers": 0,
                },
            })

            result = client.get_economics()
            call_url = mock_get.call_args[0][0]
            assert "/subscriptions/economics" in call_url
            assert "customers" in result

    def test_get_customer_economics(self):
        client = SubscriptionsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "get") as mock_get:
            mock_get.return_value = httpx.Response(200, json={
                "customer_id": "cust-1",
                "external_id": "acme",
                "plan": "Pro",
                "subscription_revenue_micros": 49_000_000,
                "usage_cost_micros": 20_000_000,
                "gross_margin_micros": 29_000_000,
                "margin_percentage": 59.18,
            })

            result = client.get_customer_economics("cust-1")
            assert result["gross_margin_micros"] == 29_000_000

    def test_get_subscription(self):
        client = SubscriptionsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "get") as mock_get:
            mock_get.return_value = httpx.Response(200, json={
                "id": "uuid-1",
                "stripe_subscription_id": "sub_abc",
                "stripe_product_name": "Pro",
                "status": "active",
                "amount_micros": 49_000_000,
                "currency": "usd",
                "interval": "month",
                "current_period_start": "2026-01-01T00:00:00Z",
                "current_period_end": "2026-02-01T00:00:00Z",
                "last_synced_at": "2026-01-15T12:00:00Z",
            })

            result = client.get_subscription("cust-1")
            assert result["status"] == "active"

    def test_get_invoices(self):
        client = SubscriptionsClient(api_key="ubb_live_test", base_url="http://localhost:8001")

        with patch.object(client._http, "get") as mock_get:
            mock_get.return_value = httpx.Response(200, json={
                "data": [], "next_cursor": None, "has_more": False,
            })

            result = client.get_invoices("cust-1")
            assert result["has_more"] is False
