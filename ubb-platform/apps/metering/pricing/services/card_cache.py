"""In-process (L1) resolved-rate cache.

L1 caches the single RESOLVED ``Rate`` instance (or ``None``, a negative
cache) per resolution key for TTL_SECONDS — one entry per (tenant, customer,
which side is being resolved, measurement_key, currency, **the as-of instant**,
full fourteen-selector tuple from ``Rate.SELECTORS``:
provider, event_type, task_type, subtask_type and the ten slots) — not a set of
candidate rows to re-match. Dimensions are declared and cardinality-capped
(design D4), so the SELECTOR half of the key is bounded: unlike the old
free-text open-bag keyspace it once bypassed L1 for, two different selector
sets can never collide and no tenant can grow that half without declaring
something first.

⚠ **THE INSTANT IS NOT BOUNDED AND NOTHING HERE PRETENDS IT IS.** An effective
moment is a microsecond-resolution timestamp, so the keyspace is now the
selector tuple's bound multiplied by however many distinct instants a worker is
asked about — one per recording call in practice, which means nearly every
entry is written and never read again. What holds the memory is what always
held it and nothing more: `_L1_MAX` clears the dict at the cap and
TTL_SECONDS expires the rest. That is a worse hit rate than a clock-read key
had, and it is the price of the key being TRUE — a key that answers for an
instant it was not built for is not a cache, it is a wrong number.

**⚠ THE KEY CARRIES THE AS-OF INSTANT, AND A PUBLISH THEREFORE INVALIDATES
NOTHING (#356).** Both halves were live defects. The resolve path read the
clock
rather than taking the event's own instant, so a cached answer was an answer
for *now* whatever moment it was asked about; and `book_service.publish` bumped
the version at publish time, which is the wrong moment when the boundary is in
the future. Invalidating "at the boundary" would need a job running at the
effective instant — the one thing forward-dated publishing exists to avoid.
Keying on the instant removes the question instead: **a cached resolution
answers for the instant it was computed for and for no other**, so entries for
instants before a new boundary stay correct forever and entries for instants
after it were never created.

⚠ **THE VERSION KEY ubb:cardver:{tenant} NOW HAS NO WRITER AT ALL, AND THAT IS
RECORDED RATHER THAN LEFT TO BE DISCOVERED.** `invalidate` had exactly one
caller — the publish above — and `Rate` has never bumped it from `save`/
`delete`, which is where `docs/conventions/django-patterns.md` says a cached
resolve's invalidation belongs. **Adding that bump is refused HERE on purpose**:
`book_service.publish` closes and opens rate rows through the model layer, so a
model-layer bump would put publish-time invalidation straight back, which is
the defect this commit deletes. The write it would legitimately catch is the
retroactive one — a rule dated into the past, which the instant in the key
cannot express — and the ticket that wires a READER is the ticket that has to
decide how such a write reaches it. Nothing is unheld meanwhile, because
nothing reads.

The version discipline itself is unchanged and is what that reader inherits:
begin_request reads the version at most once per request into a
contextvars.ContextVar — request/context-scoped, so a stale concurrent request
can never clobber the version a fresher request observed — and the L1 read
compares cached entries against it, so a bump would propagate within one request
boundary + TTL.

**Nothing in production reads this cache**, and since #356 nothing writes to it
either: the resolve path and ``begin_request`` had one caller — the accept-time
estimate deleted in #239 — and the recording path resolves cards against live
ORM through ``PricingService``. Disposing of the module belongs to a later
slice-1 ticket, with ``markup_cache.py``.
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
    def resolve_price(tenant, customer, selectors, measurement_key, currency,
                      as_of):
        """A customer price, with `PricingService`'s own semantics, via L1."""
        from apps.metering.pricing.services.pricing_service import PricingService
        return CardCache._through_l1(
            "price", tenant, customer, selectors, measurement_key, currency,
            as_of,
            lambda: PricingService.resolve_the_price_rule(
                tenant, customer, selectors, measurement_key, currency, as_of))

    @staticmethod
    def resolve_cost(tenant, selectors, measurement_key, currency, as_of):
        """A supplier cost, likewise — and with no customer, because a cost
        book is selected by supplier and currency alone (#368)."""
        from apps.metering.pricing.services.pricing_service import PricingService
        return CardCache._through_l1(
            "cost", tenant, None, selectors, measurement_key, currency, as_of,
            lambda: PricingService.resolve_the_cost_rule(
                tenant, selectors, measurement_key, currency, as_of))

    @staticmethod
    def _through_l1(side, tenant, customer, selectors, measurement_key,
                    currency, as_of, resolve):
        """The caching itself, shared by the two above.

        ⚠ **`side` IS PART OF THE KEY AND IS NOT A DISCRIMINATOR (#368).**
        A cost resolution and a price resolution for one quantity are two
        different answers, so they need two entries; what changed is that they
        are now two different QUERIES against two different tables, chosen by
        the caller above rather than by a value passed down. Nothing below
        branches on it — it is a key component, exactly like the currency.

        ``as_of`` is REQUIRED and has no default (#356). It used to be a
        ``timezone.now()`` read inside this method, which made every cached
        answer an answer about the present whatever moment the caller was
        asking about — the resolution half of the forward-dating defect, and
        the reason it is a parameter at the resolver too. A default here would
        put the same read back, one layer down and harder to see.

        The old implementation bypassed the cache whenever a
        task_type/subtask_type/slot selector was pinned, because an unbounded
        tag keyspace would poison a key that named no slot — which meant every
        event carrying a slot value hit Postgres. Grouping fields are now
        declared and cardinality-capped (design D4), so the full
        fourteen-selector tuple is a bounded, safe cache key and the bypass is
        gone. Widening the slots to ten (#276) widened the tuple and changed
        nothing about that argument: the bound is the cardinality cap per slot,
        not the slot count. The instant joins the key on the same terms — it is
        the event's own effective moment, not an unbounded free-text axis.

        Returned Rate instances are shared cache objects — callers must NOT
        mutate them."""
        from apps.metering.pricing.models import Rate
        sel_tuple = tuple(selectors.get(name) or "" for name in Rate.SELECTORS)
        ver = _ctx_versions.get({}).get(str(tenant.id), 0)
        key = (str(tenant.id), str(customer.id) if customer else "",
               side, measurement_key, currency, as_of, sel_tuple)
        hit = _l1.get(key)
        if hit and hit[0] == ver and hit[1] > time.monotonic():
            return hit[2]
        rate = resolve()
        if len(_l1) >= _L1_MAX:
            _l1.clear()  # crude bound; entries repopulate within one TTL
        _l1[key] = (ver, time.monotonic() + TTL_SECONDS, rate)
        return rate
