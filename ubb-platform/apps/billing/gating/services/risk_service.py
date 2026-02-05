from django.core.cache import cache

from apps.billing.gating.models import RiskConfig


class RiskService:
    @staticmethod
    def check(customer):
        if customer.status == "suspended":
            return {"allowed": False, "reason": "insufficient_funds"}
        if customer.status == "closed":
            return {"allowed": False, "reason": "account_closed"}
        try:
            config = customer.tenant.risk_config
        except RiskConfig.DoesNotExist:
            return {"allowed": True, "reason": None}
        # Fixed-window rate limiting
        if config.max_requests_per_minute and config.max_requests_per_minute > 0:
            cache_key = f"ratelimit:{customer.id}:rpm"
            current_count = cache.get(cache_key, 0)
            if current_count >= config.max_requests_per_minute:
                return {"allowed": False, "reason": "rate_limit_exceeded"}
            try:
                cache.incr(cache_key)
            except ValueError:
                cache.set(cache_key, 1, timeout=60)
        return {"allowed": True, "reason": None}
