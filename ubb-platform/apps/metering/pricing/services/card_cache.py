"""In-process (L1) resolved-rate cache + Redis tier-position mirror.

L1 caches the single RESOLVED ``Rate`` instance (or ``None``, a negative
cache) per tag-LESS resolution key for TTL_SECONDS — one entry per (tenant,
customer, card_type, provider, event_type, metric, currency), not a set of
candidate rows to re-match. Dimension (tag)-bearing lookups bypass L1
entirely and re-resolve every call (tags vary per event; caching a
tag-influenced result under a tag-less key would wrongly positive/negative-
cache for a different tag set — see ``resolve``). Version key
ubb:cardver:{tenant} is read at most once per request: begin_request stores
the observed version in a contextvars.ContextVar — request/context-scoped, so
a stale concurrent request can never clobber the version a fresher request
observed — and resolve compares cached entries against it. A publish-time
invalidation therefore propagates within one request boundary + TTL.
"""
import contextvars
import time

from django.conf import settings

TTL_SECONDS = 30
MIRROR_TTL_SECONDS = 62 * 24 * 3600  # month + buffer; do NOT import billing internals here
_L1_MAX = 4096    # crude bound: clear-on-full (not an LRU) caps worker memory
_l1 = {}          # key -> (version, expires_monotonic, Rate | None)
# Request-scoped {tenant_id: version} observed by begin_request. Copy-on-write:
# set() replaces the whole dict so no context ever mutates another's view.
_ctx_versions = contextvars.ContextVar("card_cache_versions")

_redis = None  # lazy singleton; bound to settings.REDIS_URL at first use


def _client():
    global _redis
    if _redis is None:
        import redis
        _redis = redis.from_url(settings.REDIS_URL)
    return _redis


def _ver_key(tenant_id):
    return f"ubb:cardver:{tenant_id}"


class CardCache:
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
    def resolve(tenant, customer, card_type, provider, event_type, metric, tags, currency):
        """Resolve with PricingService._resolve_card semantics, via the L1
        cache when tags are empty. Returned Rate instances are shared cache
        objects — callers must NOT mutate them."""
        from django.utils import timezone
        from apps.metering.pricing.services.pricing_service import PricingService
        if tags:
            # Dimension-bearing resolutions vary per tag set; caching the
            # tag-influenced result under a tag-less key would wrongly
            # negative/positive-cache for other tag sets. Bypass L1.
            return PricingService._resolve_card(
                tenant, customer, card_type, provider, event_type, metric,
                tags, currency, timezone.now())
        ver = _ctx_versions.get({}).get(str(tenant.id), 0)
        key = (str(tenant.id), str(customer.id) if customer else "",
               card_type, provider or "", event_type or "", metric, currency)
        hit = _l1.get(key)
        if hit and hit[0] == ver and hit[1] > time.monotonic():
            return hit[2]
        rate = PricingService._resolve_card(
            tenant, customer, card_type, provider, event_type, metric,
            tags, currency, timezone.now())
        if len(_l1) >= _L1_MAX:
            _l1.clear()  # crude bound; entries repopulate within one TTL
        _l1[key] = (ver, time.monotonic() + TTL_SECONDS, rate)
        return rate


class TierMirror:
    @staticmethod
    def _key(tenant_id, customer_id, lineage_id, now):
        return f"ubb:tiermirror:{tenant_id}:{customer_id}:{lineage_id}:{now:%Y-%m}"

    @staticmethod
    def read(tenant_id, customer_id, lineage_id, now):
        try:
            v = _client().get(TierMirror._key(tenant_id, customer_id, lineage_id, now))
            return int(v) if v is not None else 0
        except Exception:
            return 0  # conservative: prior=0 estimates at the FIRST tier

    @staticmethod
    def write(tenant_id, customer_id, lineage_id, units_total, now):
        try:
            _client().set(TierMirror._key(tenant_id, customer_id, lineage_id, now),
                          int(units_total), ex=MIRROR_TTL_SECONDS)
        except Exception:
            pass
