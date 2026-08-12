"""In-process (L1) resolved-rate cache.

L1 caches the single RESOLVED ``Rate`` instance (or ``None``, a negative
cache) per resolution key for TTL_SECONDS — one entry per (tenant, customer,
card_type, measurement_key, currency, full ten-selector tuple from
``Rate.SELECTORS``:
provider, event_type, task_type, subtask_type, dim1..dim6) — not a set of
candidate rows to re-match. Dimensions are declared and cardinality-capped
(design D4), so the selector tuple is a bounded, safe cache key: unlike the
old free-text open-bag keyspace it once bypassed L1 for, two different
selector sets can never collide and the keyspace itself cannot grow
unbounded. Version key ubb:cardver:{tenant} is read at most once per request:
begin_request stores the observed version in a contextvars.ContextVar —
request/context-scoped, so a stale concurrent request can never clobber the
version a fresher request observed — and resolve compares cached entries
against it. A publish-time invalidation therefore propagates within one
request boundary + TTL.

**Nothing in production reads this cache.** ``resolve`` and ``begin_request``
had one caller — the accept-time estimate deleted in #239 — and the recording
path resolves cards against live ORM through ``PricingService``. Only
``invalidate`` is still wired, from ``book_service.py``. The request-scoped
version discipline above describes how the read path worked, and is kept
because it is the contract any future reader inherits; disposing of the module
belongs to a later slice-1 ticket, with ``markup_cache.py``.
"""
import contextvars
import time

from django.conf import settings

TTL_SECONDS = 30
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
    def resolve(tenant, customer, card_type, selectors, measurement_key,
                currency):
        """Resolve with PricingService._resolve_card semantics, always via L1.

        The old implementation bypassed the cache whenever a
        task_type/subtask_type/dim1..dim6 selector was pinned, because an
        unbounded tag keyspace would poison a dimension-less key — which
        meant every dimension-bearing event hit Postgres. Dimensions are now
        declared and cardinality-capped (design D4), so the full ten-selector
        tuple is a bounded, safe cache key and the bypass is gone.

        Returned Rate instances are shared cache objects — callers must NOT
        mutate them."""
        from django.utils import timezone
        from apps.metering.pricing.models import Rate
        from apps.metering.pricing.services.pricing_service import PricingService
        sel_tuple = tuple(selectors.get(name) or "" for name in Rate.SELECTORS)
        ver = _ctx_versions.get({}).get(str(tenant.id), 0)
        key = (str(tenant.id), str(customer.id) if customer else "",
               card_type, measurement_key, currency, sel_tuple)
        hit = _l1.get(key)
        if hit and hit[0] == ver and hit[1] > time.monotonic():
            return hit[2]
        rate = PricingService._resolve_card(
            tenant, customer, card_type, selectors, measurement_key,
            currency, timezone.now())
        if len(_l1) >= _L1_MAX:
            _l1.clear()  # crude bound; entries repopulate within one TTL
        _l1[key] = (ver, time.monotonic() + TTL_SECONDS, rate)
        return rate
