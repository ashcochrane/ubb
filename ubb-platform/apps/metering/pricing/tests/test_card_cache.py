import threading
import time
from datetime import timedelta

import redis
import pytest
from django.conf import settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.metering.pricing.models import PricingBook, Rate
from apps.metering.pricing.services import card_cache as card_cache_module
from apps.metering.pricing.services.book_service import BookService
from apps.metering.pricing.services.card_cache import CardCache
from apps.metering.pricing.services.pricing_service import PricingService
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import declares_a_quantity
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
    book = PricingBook.objects.create(
        tenant=tenant, key="openai", is_default=True, version=1)
    rate = Rate.objects.create(
        tenant=tenant, provider="openai", event_type="llm_call",
        measurement=declares_a_quantity(tenant, "tokens"), currency="usd", rate_structure="per_unit",
        rate_per_unit_micros=10_000_000, unit_quantity=1_000_000,
        pricing_book=book, book_version_from=1)
    return book, rate


@pytest.fixture(autouse=True)
def _clean_ubb_redis_keys():
    """Clean up ubb:cardver:* keys this file's tests create,
    and the in-process L1 dict, so tests stay independent."""
    yield
    card_cache_module._l1.clear()
    r = redis.from_url(settings.REDIS_URL)
    for key in r.scan_iter(match="ubb:cardver:*"):
        r.delete(key)


def test_resolve_matches_pricing_service(tenant, customer, price_card_fixture):
    now = timezone.now()
    selectors = {"provider": "openai", "event_type": "llm_call"}
    expected = PricingService.resolve_the_price_rule(
        tenant, customer, selectors, "tokens", "usd", now)
    CardCache.begin_request(tenant.id)
    got = CardCache.resolve_price(tenant, customer, selectors, "tokens", "usd", now)
    assert expected is not None
    assert got is not None and got.id == expected.id


def test_second_resolve_hits_cache(tenant, customer, price_card_fixture):
    selectors = {"provider": "openai", "event_type": "llm_call"}
    now = timezone.now()
    CardCache.begin_request(tenant.id)
    CardCache.resolve_price(tenant, customer, selectors, "tokens", "usd", now)
    with CaptureQueriesContext(connection) as ctx:
        CardCache.resolve_price(tenant, customer, selectors, "tokens", "usd", now)
    assert len(ctx.captured_queries) == 0


def test_invalidate_forces_reread(tenant, customer, price_card_fixture):
    selectors = {"provider": "openai", "event_type": "llm_call"}
    now = timezone.now()
    CardCache.begin_request(tenant.id)
    CardCache.resolve_price(tenant, customer, selectors, "tokens", "usd", now)
    CardCache.invalidate(tenant.id)
    CardCache.begin_request(tenant.id)   # new request observes the bump
    with CaptureQueriesContext(connection) as ctx:
        CardCache.resolve_price(tenant, customer, selectors, "tokens", "usd", now)
    assert len(ctx.captured_queries) > 0


def test_dimensioned_card_is_cached_per_selector_set(tenant, customer):
    """A dimensioned card is still resolved correctly per selector set — but
    now (Task 13) via L1, keyed on the full ten-selector tuple, not by
    bypassing the cache. Dimensions are declared and cardinality-capped
    (design D4), so the selector tuple is a bounded, safe cache key: two
    different selector sets get separate L1 entries and never collide, and a
    repeat resolve for the SAME selector set is served from L1 with zero
    queries."""
    book = PricingBook.objects.create(
        tenant=tenant, key="dimensioned", is_default=True, version=1)
    rate_gpt4 = Rate.objects.create(
        tenant=tenant, provider="openai", event_type="llm_call",
        measurement=declares_a_quantity(tenant, "tokens"), currency="usd", grouping_field_1="gpt-4",
        rate_per_unit_micros=20_000_000, unit_quantity=1_000_000,
        pricing_book=book, book_version_from=1)
    rate_gpt35 = Rate.objects.create(
        tenant=tenant, provider="openai", event_type="llm_call",
        measurement=declares_a_quantity(tenant, "tokens"), currency="usd", grouping_field_1="gpt-3.5",
        rate_per_unit_micros=5_000_000, unit_quantity=1_000_000,
        pricing_book=book, book_version_from=1)

    now = timezone.now()
    CardCache.begin_request(tenant.id)
    got_gpt4 = CardCache.resolve_price(
        tenant, customer,
        {"provider": "openai", "event_type": "llm_call", "grouping_field_1": "gpt-4"}, "tokens", "usd", now)
    got_gpt35 = CardCache.resolve_price(
        tenant, customer,
        {"provider": "openai", "event_type": "llm_call", "grouping_field_1": "gpt-3.5"}, "tokens", "usd", now)
    assert got_gpt4 is not None and got_gpt4.id == rate_gpt4.id
    assert got_gpt35 is not None and got_gpt35.id == rate_gpt35.id

    # Different selector sets do not collide: re-resolving the first set still
    # returns the first rate, not the second's.
    with CaptureQueriesContext(connection) as ctx:
        got_gpt4_again = CardCache.resolve_price(
            tenant, customer,
            {"provider": "openai", "event_type": "llm_call", "grouping_field_1": "gpt-4"}, "tokens", "usd", now)
    assert got_gpt4_again is not None and got_gpt4_again.id == rate_gpt4.id
    assert len(ctx.captured_queries) == 0, "same selector set must be served from L1"


def test_stale_begin_request_in_other_context_does_not_clobber(tenant, customer, price_card_fixture):
    """Concurrency guard: this context observed the post-publish version; a
    stale reader storing its pre-publish observation in ANOTHER context (its
    own thread) must not clobber it — the fresh context must still re-read.
    With a shared module-level dict this test fails (stale write wins and the
    stale L1 entry is served with zero queries)."""
    selectors = {"provider": "openai", "event_type": "llm_call"}
    now = timezone.now()
    CardCache.begin_request(tenant.id)
    CardCache.resolve_price(tenant, customer, selectors, "tokens", "usd", now)

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
        got = CardCache.resolve_price(tenant, customer, selectors, "tokens", "usd", now)
    assert got is not None
    assert len(ctx.captured_queries) > 0


def test_l1_cap_clears_instead_of_growing_unbounded(tenant, customer, price_card_fixture):
    """An insert at the cap clears the L1 (crude bound) rather than growing it."""
    selectors = {"provider": "openai", "event_type": "llm_call"}
    now = timezone.now()
    CardCache.begin_request(tenant.id)
    CardCache.resolve_price(tenant, customer, selectors, "tokens", "usd", now)
    # Pad to the cap with synthetic entries.
    while len(card_cache_module._l1) < card_cache_module._L1_MAX:
        card_cache_module._l1[("pad", len(card_cache_module._l1))] = (
            0, time.monotonic() + 30, None)
    # A resolve miss (different quantity) inserts one entry -> triggers the clear.
    CardCache.resolve_price(tenant, customer, selectors, "other_metric", "usd", now)
    assert len(card_cache_module._l1) == 1


def test_a_cached_resolution_answers_for_its_own_instant_and_no_other(
        tenant, customer):
    """Two instants across a boundary, two answers, both served from L1 (#356).

    The key carries the instant, so the second resolve is not the first one's
    answer re-used for a different moment — and it is not a database read
    either, which is what makes this a statement about the CACHE rather than
    about resolution. The old key could only hold one of these two answers, and
    which one it held depended on when the entry happened to be built.
    """
    boundary = timezone.now() + timedelta(days=7)
    book = PricingBook.objects.create(
        tenant=tenant, key="openai", is_default=True, version=1)
    declaration = declares_a_quantity(tenant, "tokens")
    outgoing = Rate.objects.create(
        tenant=tenant, provider="openai",
        measurement=declaration, currency="usd", rate_per_unit_micros=10,
        pricing_book=book, book_version_from=1,
        valid_from=boundary - timedelta(days=30), valid_to=boundary)
    incoming = Rate.objects.create(
        tenant=tenant, provider="openai",
        measurement=declaration, currency="usd", rate_per_unit_micros=30,
        pricing_book=book, book_version_from=1, valid_from=boundary)
    selectors = {"provider": "openai"}
    before, after = boundary - timedelta(seconds=1), boundary + timedelta(seconds=1)

    CardCache.begin_request(tenant.id)
    CardCache.resolve_price(tenant, customer, selectors, "tokens", "usd", before)
    CardCache.resolve_price(tenant, customer, selectors, "tokens", "usd", after)

    with CaptureQueriesContext(connection) as ctx:
        cached_before = CardCache.resolve_price(
            tenant, customer, selectors, "tokens", "usd", before)
        cached_after = CardCache.resolve_price(
            tenant, customer, selectors, "tokens", "usd", after)
    assert len(ctx.captured_queries) == 0, "both answers must come from L1"
    assert cached_before.id == outgoing.id
    assert cached_after.id == incoming.id


def test_a_publish_invalidates_nothing(tenant, customer, price_card_fixture,
                                       django_capture_on_commit_callbacks):
    """The second half of the forward-dating fix, asserted rather than assumed.

    A publish used to bump the version key, which is the wrong moment when the
    boundary is in the future — and invalidating AT the boundary would need
    something to run at the effective instant, which is exactly what
    forward-dated publishing exists to avoid. With the instant in the key there
    is nothing to invalidate: entries for instants before the boundary stay
    correct forever and entries after it were never created.

    Asserted two ways, because either alone is weak. The version key is never
    written, which is the mechanism; and an entry built before the publish is
    still served from L1 afterwards, which is what the mechanism buys.
    """
    book, _ = price_card_fixture
    now = timezone.now()
    selectors = {"provider": "openai", "event_type": "llm_call"}
    version_key = f"ubb:cardver:{tenant.id}"
    r = redis.from_url(settings.REDIS_URL)
    assert r.get(version_key) is None

    CardCache.begin_request(tenant.id)
    CardCache.resolve_price(tenant, customer, selectors, "tokens", "usd", now)

    with django_capture_on_commit_callbacks(execute=True):
        # THE ONE MUTATION SURFACE A BOOK HAS (#368). The atomic reprice this
        # used to call is deleted with the audit action it wrote; a change is
        # declared and published, which is the same write to the same rows and
        # is what the cache is being asked about.
        BookService.publish_declared(BookService.declare(book, [{
            "kind": "reprice",
            "measurement_key": "tokens", "provider": "openai",
            "event_type": "llm_call", "rate_per_unit_micros": 20_000_000,
        }]))

    assert r.get(version_key) is None, "a publish must not bump the version"
    CardCache.begin_request(tenant.id)
    with CaptureQueriesContext(connection) as ctx:
        CardCache.resolve_price(tenant, customer, selectors, "tokens", "usd", now)
    assert len(ctx.captured_queries) == 0, (
        "the entry built before the publish still answers for its own instant")
