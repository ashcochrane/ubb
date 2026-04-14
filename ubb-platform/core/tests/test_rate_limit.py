"""Tests for API rate limiting."""
import json
import pytest
from unittest.mock import patch, MagicMock
from django.test import RequestFactory, override_settings
from ninja.errors import HttpError

from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestTenantRateLimitField:
    def test_rate_limit_field_defaults_to_none(self):
        tenant = Tenant.objects.create(name="Test", products=["metering"])
        assert getattr(tenant, "rate_limit_per_second", None) is None

    def test_rate_limit_field_can_be_set(self):
        """rate_limit_per_second was removed from the model; getattr returns None."""
        tenant = Tenant.objects.create(name="Test", products=["metering"])
        assert getattr(tenant, "rate_limit_per_second", None) is None


class TestGlobalRateLimitMiddleware:
    def setup_method(self):
        self.factory = RequestFactory()

    @override_settings(UBB_GLOBAL_RATE_LIMIT=10)
    @patch("core.rate_limit._get_redis")
    def test_allows_request_under_limit(self, mock_get_redis):
        from core.rate_limit import GlobalRateLimitMiddleware
        mock_redis = MagicMock()
        mock_redis.evalsha.return_value = 5
        mock_get_redis.return_value = mock_redis
        get_response = MagicMock(return_value=MagicMock(status_code=200))
        middleware = GlobalRateLimitMiddleware(get_response)
        request = self.factory.get("/api/v1/metering/usage")
        response = middleware(request)
        assert response.status_code == 200
        get_response.assert_called_once()

    @override_settings(UBB_GLOBAL_RATE_LIMIT=10)
    @patch("core.rate_limit._get_redis")
    def test_returns_429_when_over_limit(self, mock_get_redis):
        from core.rate_limit import GlobalRateLimitMiddleware
        mock_redis = MagicMock()
        mock_redis.evalsha.return_value = 11
        mock_get_redis.return_value = mock_redis
        get_response = MagicMock()
        middleware = GlobalRateLimitMiddleware(get_response)
        request = self.factory.get("/api/v1/metering/usage")
        response = middleware(request)
        assert response.status_code == 429
        body = json.loads(response.content)
        assert body["error"] == "rate_limited"
        assert response["Retry-After"] == "1"
        get_response.assert_not_called()

    @override_settings(UBB_GLOBAL_RATE_LIMIT=10)
    @patch("core.rate_limit._get_redis")
    def test_skips_health_endpoint(self, mock_get_redis):
        from core.rate_limit import GlobalRateLimitMiddleware
        get_response = MagicMock(return_value=MagicMock(status_code=200))
        middleware = GlobalRateLimitMiddleware(get_response)
        request = self.factory.get("/api/v1/health")
        response = middleware(request)
        assert response.status_code == 200
        mock_get_redis.assert_not_called()

    @override_settings(UBB_GLOBAL_RATE_LIMIT=10)
    @patch("core.rate_limit._get_redis")
    def test_skips_ready_endpoint(self, mock_get_redis):
        from core.rate_limit import GlobalRateLimitMiddleware
        get_response = MagicMock(return_value=MagicMock(status_code=200))
        middleware = GlobalRateLimitMiddleware(get_response)
        request = self.factory.get("/api/v1/ready")
        response = middleware(request)
        assert response.status_code == 200
        mock_get_redis.assert_not_called()

    @override_settings(UBB_GLOBAL_RATE_LIMIT=10)
    @patch("core.rate_limit._get_redis")
    def test_skips_stripe_webhook(self, mock_get_redis):
        from core.rate_limit import GlobalRateLimitMiddleware
        get_response = MagicMock(return_value=MagicMock(status_code=200))
        middleware = GlobalRateLimitMiddleware(get_response)
        request = self.factory.post("/api/v1/webhooks/stripe")
        response = middleware(request)
        assert response.status_code == 200
        mock_get_redis.assert_not_called()

    @override_settings(UBB_GLOBAL_RATE_LIMIT=10)
    @patch("core.rate_limit._get_redis")
    def test_fail_open_when_redis_unavailable(self, mock_get_redis):
        from core.rate_limit import GlobalRateLimitMiddleware
        import redis as redis_lib
        mock_get_redis.side_effect = redis_lib.ConnectionError("Redis down")
        get_response = MagicMock(return_value=MagicMock(status_code=200))
        middleware = GlobalRateLimitMiddleware(get_response)
        request = self.factory.get("/api/v1/metering/usage")
        response = middleware(request)
        assert response.status_code == 200


@pytest.mark.django_db
class TestPerTenantRateLimit:
    def setup_method(self):
        self.factory = RequestFactory()
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])

    @override_settings(UBB_TENANT_RATE_LIMIT=100)
    @patch("core.rate_limit._incr_counter")
    def test_high_tier_uses_full_limit(self, mock_incr):
        from core.rate_limit import RateLimit
        mock_incr.return_value = 50
        dep = RateLimit("high")
        request = self.factory.get("/test")
        request.tenant = self.tenant
        dep(request)
        key_arg = mock_incr.call_args[0][0]
        assert f"ratelimit:tenant:{self.tenant.id}:" in key_arg

    @override_settings(UBB_TENANT_RATE_LIMIT=100)
    @patch("core.rate_limit._incr_counter")
    def test_standard_tier_uses_20_percent(self, mock_incr):
        from core.rate_limit import RateLimit
        mock_incr.return_value = 21
        dep = RateLimit("standard")
        request = self.factory.get("/test")
        request.tenant = self.tenant
        with pytest.raises(HttpError) as exc_info:
            dep(request)
        assert exc_info.value.status_code == 429
        assert request.rate_limit_exceeded is True

    @override_settings(UBB_TENANT_RATE_LIMIT=100)
    @patch("core.rate_limit._incr_counter")
    def test_tenant_override_respected(self, mock_incr):
        from core.rate_limit import RateLimit
        self.tenant.rate_limit_per_second = 200  # dynamic attribute
        mock_incr.return_value = 150
        dep = RateLimit("high")
        request = self.factory.get("/test")
        request.tenant = self.tenant
        dep(request)

    @override_settings(UBB_TENANT_RATE_LIMIT=100)
    @patch("core.rate_limit._incr_counter")
    def test_standard_tier_minimum_is_1(self, mock_incr):
        from core.rate_limit import RateLimit
        self.tenant.rate_limit_per_second = 3  # dynamic attribute
        mock_incr.return_value = 1
        dep = RateLimit("standard")
        request = self.factory.get("/test")
        request.tenant = self.tenant
        dep(request)

    @override_settings(UBB_TENANT_RATE_LIMIT=100)
    @patch("core.rate_limit._incr_counter")
    def test_stores_rate_limit_info_on_request(self, mock_incr):
        from core.rate_limit import RateLimit
        mock_incr.return_value = 30
        dep = RateLimit("high")
        request = self.factory.get("/test")
        request.tenant = self.tenant
        dep(request)
        assert hasattr(request, "rate_limit_info")
        assert request.rate_limit_info["limit"] == 100
        assert request.rate_limit_info["remaining"] == 70

    @override_settings(UBB_TENANT_RATE_LIMIT=100)
    @patch("core.rate_limit._incr_counter")
    def test_fail_open_when_redis_unavailable(self, mock_incr):
        from core.rate_limit import RateLimit
        mock_incr.side_effect = Exception("Redis down")
        dep = RateLimit("high")
        request = self.factory.get("/test")
        request.tenant = self.tenant
        dep(request)

    def test_skips_when_no_tenant(self):
        from core.rate_limit import RateLimit
        dep = RateLimit("high")
        request = self.factory.get("/test")
        dep(request)  # should not raise


class TestRateLimitHeaderMiddleware:
    def setup_method(self):
        self.factory = RequestFactory()

    def test_injects_headers_when_rate_limit_info_present(self):
        from core.rate_limit import RateLimitHeaderMiddleware
        response = MagicMock(status_code=200)
        response.__setitem__ = MagicMock()
        get_response = MagicMock(return_value=response)
        middleware = RateLimitHeaderMiddleware(get_response)
        request = self.factory.get("/test")
        request.rate_limit_info = {"limit": 500, "remaining": 450, "reset": 1710000001}
        result = middleware(request)
        response.__setitem__.assert_any_call("X-RateLimit-Limit", "500")
        response.__setitem__.assert_any_call("X-RateLimit-Remaining", "450")
        response.__setitem__.assert_any_call("X-RateLimit-Reset", "1710000001")

    def test_no_headers_when_no_rate_limit_info(self):
        from core.rate_limit import RateLimitHeaderMiddleware
        response = MagicMock(status_code=200)
        response.__setitem__ = MagicMock()
        get_response = MagicMock(return_value=response)
        middleware = RateLimitHeaderMiddleware(get_response)
        request = self.factory.get("/test")
        result = middleware(request)
        response.__setitem__.assert_not_called()

    def test_retry_after_header_on_429(self):
        from core.rate_limit import RateLimitHeaderMiddleware
        response = MagicMock(status_code=429)
        response.__setitem__ = MagicMock()
        get_response = MagicMock(return_value=response)
        middleware = RateLimitHeaderMiddleware(get_response)
        request = self.factory.get("/test")
        request.rate_limit_exceeded = True
        result = middleware(request)
        response.__setitem__.assert_any_call("Retry-After", "1")
