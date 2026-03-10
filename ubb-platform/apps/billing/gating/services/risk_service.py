from django.core.cache import cache

from apps.billing.gating.models import RiskConfig


class RiskService:
    @staticmethod
    def check(customer, create_run=False, run_metadata=None, external_run_id=""):
        if customer.status == "suspended":
            return {"allowed": False, "reason": "insufficient_funds", "balance_micros": None, "run_id": None}
        if customer.status == "closed":
            return {"allowed": False, "reason": "account_closed", "balance_micros": None, "run_id": None}
        try:
            config = customer.tenant.risk_config
        except RiskConfig.DoesNotExist:
            config = None
        # Fixed-window rate limiting (degrades gracefully if Redis is down)
        if config and config.max_requests_per_minute and config.max_requests_per_minute > 0:
            try:
                cache_key = f"ratelimit:{customer.id}:rpm"
                current_count = cache.get(cache_key, 0)
                if current_count >= config.max_requests_per_minute:
                    return {"allowed": False, "reason": "rate_limit_exceeded", "balance_micros": None, "run_id": None}
                try:
                    cache.incr(cache_key)
                except ValueError:
                    cache.set(cache_key, 1, timeout=60)
            except Exception:
                pass  # Degrade: skip rate limiting if cache is unavailable

        # Affordability check
        from apps.billing.wallets.models import Wallet
        try:
            wallet = Wallet.objects.get(customer=customer)
            balance = wallet.balance_micros
        except Wallet.DoesNotExist:
            balance = 0

        from apps.billing.queries import get_customer_min_balance
        threshold = get_customer_min_balance(customer.id, customer.tenant_id)
        if balance < -threshold:
            return {"allowed": False, "reason": "insufficient_funds", "balance_micros": balance, "run_id": None}

        result = {"allowed": True, "reason": None, "balance_micros": balance, "run_id": None}

        # Optionally create a Run, snapshotting wallet balance and billing config limits
        if create_run:
            from apps.billing.queries import get_billing_config
            from apps.platform.runs.services import RunService

            billing_config = get_billing_config(customer.tenant_id)
            run = RunService.create_run(
                tenant=customer.tenant,
                customer=customer,
                balance_snapshot_micros=balance,
                cost_limit_micros=billing_config.run_cost_limit_micros,
                hard_stop_balance_micros=billing_config.hard_stop_balance_micros,
                metadata=run_metadata or {},
                external_run_id=external_run_id,
            )
            result["run_id"] = str(run.id)
            result["cost_limit_micros"] = run.cost_limit_micros
            result["hard_stop_balance_micros"] = run.hard_stop_balance_micros

        return result
