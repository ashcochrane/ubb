"""In-process (L1) resolved-markup cache, mirroring card_cache.py as-built.

L1 caches the single RESOLVED ``TenantMarkup`` instance (or ``None``, a
negative cache — "no markup configured" is the common case and must also be
one dict hit) per (tenant, customer) key for TTL_SECONDS. Version key
ubb:markupver:{tenant} is read at most once per request: begin_request pins
the observed version in a contextvars.ContextVar (request-scoped — a stale
concurrent request can never clobber a fresher request's view) and resolve
compares cached entries against it. TenantMarkup.save()/.delete() bump the
version at the MODEL layer so no write path can bypass invalidation; a bump
therefore propagates within one request boundary + TTL.

Money rule (never-under-hold): a missing markup would under-ESTIMATE and
therefore under-hold, so every fallback — L1 miss, stale version, Redis
failure — is a live ORM resolve via MarkupService.resolve, never "assume no
markup". The settle path does not use this cache at all (exact live-ORM
pricing via PricingService, unchanged).
"""
import contextvars
import time

from django.conf import settings

TTL_SECONDS = 30
_L1_MAX = 4096   # crude bound: clear-on-full (not an LRU), mirrors CardCache
_l1 = {}         # (tenant_id, customer_id) -> (version, expires_monotonic, TenantMarkup | None)
_ctx_versions = contextvars.ContextVar("markup_cache_versions")

_redis = None  # lazy singleton; bound to settings.REDIS_URL at first use


def _client():
    global _redis
    if _redis is None:
        import redis
        _redis = redis.from_url(settings.REDIS_URL)
    return _redis


def _ver_key(tenant_id):
    return f"ubb:markupver:{tenant_id}"


class MarkupCache:
    @staticmethod
    def begin_request(tenant_id):
        try:
            v = _client().get(_ver_key(tenant_id))
            ver = int(v) if v else 0
        except Exception:
            ver = 0  # fail-open: TTL still bounds staleness
        _ctx_versions.set({**_ctx_versions.get({}), str(tenant_id): ver})

    @staticmethod
    def invalidate(tenant_id):
        try:
            _client().incr(_ver_key(tenant_id))
        except Exception:
            pass  # TTL bounds staleness

    @staticmethod
    def resolve(tenant, customer):
        """MarkupService.resolve via the L1 cache. Returned TenantMarkup
        instances are shared cache objects — callers must NOT mutate them."""
        from apps.metering.pricing.services.markup_service import MarkupService
        ver = _ctx_versions.get({}).get(str(tenant.id), 0)
        key = (str(tenant.id), str(customer.id) if customer else "")
        hit = _l1.get(key)
        if hit and hit[0] == ver and hit[1] > time.monotonic():
            return hit[2]
        markup = MarkupService.resolve(tenant, customer)
        if len(_l1) >= _L1_MAX:
            _l1.clear()  # crude bound; entries repopulate within one TTL
        _l1[key] = (ver, time.monotonic() + TTL_SECONDS, markup)
        return markup

    @staticmethod
    def apply(provider_cost_micros, *, tenant, customer):
        """MarkupService.apply semantics via the cache (estimation hot path)."""
        markup = MarkupCache.resolve(tenant, customer)
        if markup is None:
            return provider_cost_micros
        return provider_cost_micros + markup.calculate_markup_micros(provider_cost_micros)
