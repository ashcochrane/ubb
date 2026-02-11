from django.core.cache import cache

from apps.billing.gating.models import RiskConfig


class RiskService:
    @staticmethod
    def check(customer):
        if customer.status == "suspended":
            return {"allowed": False, "reason": "insufficient_funds", "balance_micros": None}
        if customer.status == "closed":
            return {"allowed": False, "reason": "account_closed", "balance_micros": None}
        try:
            config = customer.tenant.risk_config
        except RiskConfig.DoesNotExist:
            config = None
        # Fixed-window rate limiting
        if config and config.max_requests_per_minute and config.max_requests_per_minute > 0:
            cache_key = f"ratelimit:{customer.id}:rpm"
            current_count = cache.get(cache_key, 0)
            if current_count >= config.max_requests_per_minute:
                return {"allowed": False, "reason": "rate_limit_exceeded", "balance_micros": None}
            try:
                cache.incr(cache_key)
            except ValueError:
                cache.set(cache_key, 1, timeout=60)

        # Affordability check
        from apps.billing.wallets.models import Wallet
        try:
            wallet = Wallet.objects.get(customer=customer)
            balance = wallet.balance_micros
        except Wallet.DoesNotExist:
            balance = 0

        threshold = customer.get_arrears_threshold()
        if balance < -threshold:
            return {"allowed": False, "reason": "insufficient_funds", "balance_micros": balance}

        return {"allowed": True, "reason": None, "balance_micros": balance}
