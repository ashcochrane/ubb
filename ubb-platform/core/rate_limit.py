"""API rate limiting: global middleware + per-tenant dependency.

Uses Redis fixed-window counters with atomic Lua script.
Fails open if Redis is unavailable.
"""
from __future__ import annotations

import logging
import time

import redis
from django.conf import settings
from django.http import JsonResponse
from ninja.errors import HttpError

logger = logging.getLogger("core.rate_limit")

# Lua script: atomic INCR + conditional EXPIRE
_LUA_INCR_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""

_SKIP_PATHS = {
    "/api/v1/health",
    "/api/v1/ready",
    "/api/v1/webhooks/stripe",
    "/api/v1/subscriptions/webhooks/stripe",
}

_redis_client = None
_lua_sha = None


def _get_redis():
    """Get or create a Redis client from settings.REDIS_URL."""
    global _redis_client, _lua_sha
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        _lua_sha = _redis_client.script_load(_LUA_INCR_SCRIPT)
    return _redis_client


def _incr_counter(key: str, window_seconds: int = 2) -> int:
    """Atomically increment a counter and set expiry. Returns new count.

    TTL is 2s (not 1s) as a safety margin — ensures the key outlives the
    1-second window even with minor clock skew or Redis lag.
    """
    r = _get_redis()
    return r.evalsha(_lua_sha, 1, key, window_seconds)


class GlobalRateLimitMiddleware:
    """Pre-auth rate limit on all inbound requests.

    Uses a 1-second fixed window. Returns 429 if global limit exceeded.
    Skips health/ready endpoints. Fails open if Redis is unavailable.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path in _SKIP_PATHS:
            return self.get_response(request)

        limit = getattr(settings, "UBB_GLOBAL_RATE_LIMIT", 5000)
        try:
            window_ts = int(time.time())
            key = f"ratelimit:global:{window_ts}"
            count = _incr_counter(key)
        except Exception:
            logger.warning("Redis unavailable for global rate limit — failing open")
            return self.get_response(request)

        if count > limit:
            return JsonResponse(
                {"error": "rate_limited", "detail": "Global rate limit exceeded"},
                status=429,
                headers={"Retry-After": "1"},
            )

        return self.get_response(request)


class RateLimit:
    """Per-tenant rate limit dependency for django-ninja endpoints.

    Usage:
        _rate_limit = RateLimit("high")      # full tenant limit
        _rate_limit = RateLimit("standard")   # 20% of tenant limit
    """

    def __init__(self, tier: str = "standard"):
        if tier not in ("high", "standard"):
            raise ValueError(f"Invalid tier: {tier}")
        self.tier = tier

    def __call__(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return

        base_limit = getattr(tenant, "rate_limit_per_second", None) or getattr(
            settings, "UBB_TENANT_RATE_LIMIT", 500
        )
        if self.tier == "high":
            limit = base_limit
        else:
            limit = max(1, base_limit // 5)

        window_ts = int(time.time())
        key = f"ratelimit:tenant:{tenant.id}:{window_ts}"

        try:
            count = _incr_counter(key)
        except Exception:
            logger.warning(
                "Redis unavailable for tenant rate limit — failing open",
                extra={"tenant_id": str(tenant.id)},
            )
            return

        remaining = max(0, limit - count)
        reset_ts = window_ts + 1

        request.rate_limit_info = {
            "limit": limit,
            "remaining": remaining,
            "reset": reset_ts,
        }

        if count > limit:
            request.rate_limit_exceeded = True
            raise HttpError(429, "Rate limit exceeded")


class RateLimitHeaderMiddleware:
    """Injects X-RateLimit-* headers on responses.

    Reads rate_limit_info stored on request by the RateLimit dependency.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        info = getattr(request, "rate_limit_info", None)
        if info:
            response["X-RateLimit-Limit"] = str(info["limit"])
            response["X-RateLimit-Remaining"] = str(info["remaining"])
            response["X-RateLimit-Reset"] = str(info["reset"])
        if response.status_code == 429 and getattr(request, "rate_limit_exceeded", False):
            response["Retry-After"] = "1"
        return response
