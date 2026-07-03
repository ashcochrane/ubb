import redis
import pytest
from django.conf import settings
from django.utils import timezone

from apps.metering.pricing.models import Rate, RateCard
from apps.metering.pricing.services import card_cache as card_cache_module
from apps.metering.pricing.services.card_cache import CardCache, TierMirror
from apps.metering.pricing.services.estimation_service import (
    EstimationService, Unpriceable)
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


@pytest.fixture
def graduated_card_fixture(tenant):
    """A default price book with one graduated (tiered) Rate, decreasing
    ladder per the brief: 10/unit up to 1_000_000 units, then 8/unit."""
    book = RateCard.objects.create(
        tenant=tenant, card_type="price", provider_key="openai", currency="usd",
        key="openai-graduated", is_default=True, version=1)
    rate = Rate.objects.create(
        tenant=tenant, card_type="price", provider="openai", event_type="llm_call",
        metric_name="tokens", currency="usd", pricing_model="graduated",
        tiers=[
            {"up_to": 1_000_000, "rate_per_unit_micros": 10_000_000},
            {"up_to": None, "rate_per_unit_micros": 8_000_000},
        ],
        rate_card=book, book_version_from=1)
    return rate


@pytest.fixture(autouse=True)
def _clean_ubb_redis_keys():
    """Clean up ubb:cardver:* / ubb:tiermirror:* keys this file's tests
    create, and the in-process L1 dict, so tests stay independent."""
    yield
    card_cache_module._l1.clear()
    r = redis.from_url(settings.REDIS_URL)
    for pattern in ("ubb:cardver:*", "ubb:tiermirror:*"):
        for key in r.scan_iter(match=pattern):
            r.delete(key)


def test_caller_billed_is_exact(tenant, customer):
    e = EstimationService.estimate(
        tenant, customer, event_type="x", provider="", usage_metrics=None,
        tags=None, currency="usd", caller_billed=777, caller_provider_cost=None,
        units=None, now=timezone.now())
    assert (e.micros, e.exact) == (777, True)


def test_linear_estimate_equals_exact_price(tenant, customer, price_card_fixture):
    CardCache.begin_request(tenant.id)
    now = timezone.now()
    e = EstimationService.estimate(
        tenant, customer, event_type="llm_call", provider="openai",
        usage_metrics={"tokens": 12_000}, tags={}, currency="usd",
        caller_billed=None, caller_provider_cost=None, units=None, now=now)
    _, exact_billed, _ = PricingService.price(
        tenant=tenant, customer=customer, event_type="llm_call", provider="openai",
        usage_metrics={"tokens": 12_000}, tags={}, currency="usd",
        caller_provider_cost=None, caller_billed=None)
    assert e.micros == exact_billed and e.exact is True


@pytest.mark.parametrize("prior_mirror,units", [(0, 50), (900_000, 250_000), (2_000_000, 10)])
def test_tiered_never_under_holds(tenant, customer, graduated_card_fixture, prior_mirror, units):
    """PROPERTY: estimate >= exact marginal price at ANY true ladder position
    <= mirror (mirror lags truth only when settles are pending, and pending
    settles only RAISE the true position; estimate at max(prior,0) covers it)."""
    now = timezone.now()
    card = graduated_card_fixture
    TierMirror.write(tenant.id, customer.id, str(card.lineage_id), prior_mirror, now)
    CardCache.begin_request(tenant.id)
    e = EstimationService.estimate(
        tenant, customer, event_type="llm_call", provider="openai",
        usage_metrics={"tokens": units}, tags={}, currency="usd",
        caller_billed=None, caller_provider_cost=None, units=None, now=now)
    for true_prior in (0, prior_mirror // 2, prior_mirror):
        assert e.micros >= card.compute_marginal(true_prior, units)


def test_unpriceable_raises(tenant, customer):
    CardCache.begin_request(tenant.id)
    with pytest.raises(Unpriceable):
        EstimationService.estimate(
            tenant, customer, event_type="unknown", provider="",
            usage_metrics={"mystery": 5}, tags={}, currency="usd",
            caller_billed=None, caller_provider_cost=None, units=None,
            now=timezone.now())
