import threading
import time

import redis
import pytest
from django.conf import settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.metering.pricing.models import Rate, RateCard
from apps.metering.pricing.services import card_cache as card_cache_module
from apps.metering.pricing.services.book_service import BookService
from apps.metering.pricing.services.card_cache import CardCache, TierMirror
from apps.metering.pricing.services.pricing_service import PricingService
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="T", default_currency="usd")


@pytest.fixture
def customer(tenant):
    return Customer.objects.create(tenant=tenant, external_id="c1")


@pytest.fixture
def price_card_fixture(tenant):
    """A default (is_default=True) price book with one per_unit Rate, matching
    the brief's construction idiom (mirrors rate_in_default_book())."""
    book = RateCard.objects.create(
        tenant=tenant, card_type="price", provider_key="openai", currency="usd",
        key="openai", is_default=True, version=1)
    rate = Rate.objects.create(
        tenant=tenant, card_type="price", provider="openai", event_type="llm_call",
        metric_name="tokens", currency="usd", pricing_model="per_unit",
        rate_per_unit_micros=10_000_000, unit_quantity=1_000_000,
        rate_card=book, book_version_from=1)
    return book, rate


@pytest.fixture(autouse=True)
def _clean_ubb_redis_keys():
    """Clean up ubb:cardver:* / ubb:tiermirror:* keys this file's tests create,
    and the in-process L1 dict, so tests stay independent."""
    yield
    card_cache_module._l1.clear()
    r = redis.from_url(settings.REDIS_URL)
    for pattern in ("ubb:cardver:*", "ubb:tiermirror:*"):
        for key in r.scan_iter(match=pattern):
            r.delete(key)


def test_resolve_matches_pricing_service(tenant, customer, price_card_fixture):
    now = timezone.now()
    expected = PricingService._resolve_card(
        tenant, customer, "price", "openai", "llm_call", "tokens", {}, "usd", now)
    CardCache.begin_request(tenant.id)
    got = CardCache.resolve(tenant, customer, "price", "openai", "llm_call",
                             "tokens", {}, "usd")
    assert expected is not None
    assert got is not None and got.id == expected.id


def test_second_resolve_hits_cache(tenant, customer, price_card_fixture):
    CardCache.begin_request(tenant.id)
    CardCache.resolve(tenant, customer, "price", "openai", "llm_call", "tokens", {}, "usd")
    with CaptureQueriesContext(connection) as ctx:
        CardCache.resolve(tenant, customer, "price", "openai", "llm_call", "tokens", {}, "usd")
    assert len(ctx.captured_queries) == 0


def test_invalidate_forces_reread(tenant, customer, price_card_fixture):
    CardCache.begin_request(tenant.id)
    CardCache.resolve(tenant, customer, "price", "openai", "llm_call", "tokens", {}, "usd")
    CardCache.invalidate(tenant.id)
    CardCache.begin_request(tenant.id)   # new request observes the bump
    with CaptureQueriesContext(connection) as ctx:
        CardCache.resolve(tenant, customer, "price", "openai", "llm_call", "tokens", {}, "usd")
    assert len(ctx.captured_queries) > 0


def test_dimensioned_card_bypasses_l1_for_different_tag_sets(tenant, customer):
    """Guard: a dimensioned card must re-match per call. If the resolved Rate
    were cached under a tag-less key, the first tag set's result would be
    wrongly returned for the second (different) tag set."""
    book = RateCard.objects.create(
        tenant=tenant, card_type="price", provider_key="openai", currency="usd",
        key="dimensioned", is_default=True, version=1)
    rate_gpt4 = Rate.objects.create(
        tenant=tenant, card_type="price", provider="openai", event_type="llm_call",
        metric_name="tokens", currency="usd", dimensions={"model": "gpt-4"},
        rate_per_unit_micros=20_000_000, unit_quantity=1_000_000,
        rate_card=book, book_version_from=1)
    rate_gpt35 = Rate.objects.create(
        tenant=tenant, card_type="price", provider="openai", event_type="llm_call",
        metric_name="tokens", currency="usd", dimensions={"model": "gpt-3.5"},
        rate_per_unit_micros=5_000_000, unit_quantity=1_000_000,
        rate_card=book, book_version_from=1)

    CardCache.begin_request(tenant.id)
    got_gpt4 = CardCache.resolve(tenant, customer, "price", "openai", "llm_call",
                                  "tokens", {"model": "gpt-4"}, "usd")
    got_gpt35 = CardCache.resolve(tenant, customer, "price", "openai", "llm_call",
                                   "tokens", {"model": "gpt-3.5"}, "usd")
    assert got_gpt4 is not None and got_gpt4.id == rate_gpt4.id
    assert got_gpt35 is not None and got_gpt35.id == rate_gpt35.id


def test_stale_begin_request_in_other_context_does_not_clobber(tenant, customer, price_card_fixture):
    """Concurrency guard: this context observed the post-publish version; a
    stale reader storing its pre-publish observation in ANOTHER context (its
    own thread) must not clobber it — the fresh context must still re-read.
    With a shared module-level dict this test fails (stale write wins and the
    stale L1 entry is served with zero queries)."""
    CardCache.begin_request(tenant.id)
    CardCache.resolve(tenant, customer, "price", "openai", "llm_call", "tokens", {}, "usd")

    CardCache.invalidate(tenant.id)
    CardCache.begin_request(tenant.id)  # fresh: observes the bumped version

    # Stale reader: its Redis GET happened BEFORE the publish (simulated by a
    # stub client returning None) and its store lands now, AFTER the fresh
    # observation above, in its own thread and therefore its own context.
    class _PrePublishClient:
        def get(self, key):
            return None  # version key did not exist pre-publish

    original_client = card_cache_module._client
    card_cache_module._client = lambda: _PrePublishClient()
    try:
        t = threading.Thread(target=CardCache.begin_request, args=(tenant.id,))
        t.start()
        t.join()
    finally:
        card_cache_module._client = original_client

    # The L1 entry was cached at the pre-publish version; the fresh context's
    # observation survived the stale store, so resolve re-reads the DB.
    with CaptureQueriesContext(connection) as ctx:
        got = CardCache.resolve(tenant, customer, "price", "openai", "llm_call",
                                "tokens", {}, "usd")
    assert got is not None
    assert len(ctx.captured_queries) > 0


def test_l1_cap_clears_instead_of_growing_unbounded(tenant, customer, price_card_fixture):
    """An insert at the cap clears the L1 (crude bound) rather than growing it."""
    CardCache.begin_request(tenant.id)
    CardCache.resolve(tenant, customer, "price", "openai", "llm_call", "tokens", {}, "usd")
    # Pad to the cap with synthetic entries.
    while len(card_cache_module._l1) < card_cache_module._L1_MAX:
        card_cache_module._l1[("pad", len(card_cache_module._l1))] = (
            0, time.monotonic() + 30, None)
    # A resolve miss (different metric) inserts one entry -> triggers the clear.
    CardCache.resolve(tenant, customer, "price", "openai", "llm_call",
                      "other_metric", {}, "usd")
    assert len(card_cache_module._l1) == 1


def test_tier_mirror_roundtrip(tenant, customer):
    now = timezone.now()
    assert TierMirror.read(tenant.id, customer.id, "lin1", now) == 0
    TierMirror.write(tenant.id, customer.id, "lin1", 900_000, now)
    assert TierMirror.read(tenant.id, customer.id, "lin1", now) == 900_000


def test_publish_bumps_card_version_on_commit(tenant, django_capture_on_commit_callbacks):
    book = RateCard.objects.create(
        tenant=tenant, card_type="price", provider_key="openai", currency="usd",
        key="openai", is_default=True, version=1)
    Rate.objects.create(
        tenant=tenant, card_type="price", provider="openai", metric_name="tokens",
        currency="usd", rate_per_unit_micros=10_000_000, rate_card=book,
        book_version_from=1)
    r = redis.from_url(settings.REDIS_URL)
    key = f"ubb:cardver:{tenant.id}"
    assert r.get(key) is None

    with django_capture_on_commit_callbacks(execute=True):
        BookService.publish(book, changes=[{
            "metric_name": "tokens", "provider": "openai", "event_type": "",
            "dimensions": {}, "rate_per_unit_micros": 20_000_000,
        }])

    assert int(r.get(key)) == 1
