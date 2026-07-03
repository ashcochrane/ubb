"""In-process (L1) rate-card candidate cache + Redis tier-position mirror.

L1 caches the CANDIDATE Rate rows per resolution key for TTL_SECONDS;
dimension matching runs per call (tags vary per event). Version key
ubb:cardver:{tenant} is checked once per request (begin_request), so a
publish-time invalidation propagates within one request boundary + TTL.
"""
import time
from django.conf import settings

TTL_SECONDS = 30
MIRROR_TTL_SECONDS = 62 * 24 * 3600  # month + buffer; do NOT import billing internals here
_l1 = {}          # key -> (version, expires_monotonic, [Rate])
_req_version = {} # tenant_id -> version observed by begin_request


def _client():
    import redis
    return redis.from_url(settings.REDIS_URL)


def _ver_key(tenant_id):
    return f"ubb:cardver:{tenant_id}"


class CardCache:
    @staticmethod
    def begin_request(tenant_id):
        try:
            v = _client().get(_ver_key(tenant_id))
            _req_version[str(tenant_id)] = int(v) if v else 0
        except Exception:
            _req_version[str(tenant_id)] = 0  # fail-open: TTL still bounds staleness

    @staticmethod
    def invalidate(tenant_id):
        try:
            _client().incr(_ver_key(tenant_id))
        except Exception:
            pass  # TTL bounds staleness

    @staticmethod
    def resolve(tenant, customer, card_type, provider, event_type, metric, tags, currency):
        from django.utils import timezone
        from apps.metering.pricing.services.pricing_service import PricingService
        if tags:
            # Dimension-bearing resolutions vary per tag set; caching the
            # tag-influenced result under a tag-less key would wrongly
            # negative/positive-cache for other tag sets. Bypass L1.
            return PricingService._resolve_card(
                tenant, customer, card_type, provider, event_type, metric,
                tags, currency, timezone.now())
        ver = _req_version.get(str(tenant.id), 0)
        key = (str(tenant.id), str(customer.id) if customer else "",
               card_type, provider or "", event_type or "", metric, currency)
        hit = _l1.get(key)
        if hit and hit[0] == ver and hit[1] > time.monotonic():
            return hit[2]
        rate = PricingService._resolve_card(
            tenant, customer, card_type, provider, event_type, metric,
            tags, currency, timezone.now())
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
