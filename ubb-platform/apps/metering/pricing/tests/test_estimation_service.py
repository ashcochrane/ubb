import redis
import pytest
from django.conf import settings

from apps.metering.pricing.models import Rate, RateCard, TenantMarkup
from apps.metering.pricing.services import card_cache as card_cache_module
from apps.metering.pricing.services.card_cache import CardCache
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


@pytest.fixture(autouse=True)
def _clean_ubb_redis_keys():
    """Clean up ubb:cardver:* keys this file's tests create, and the
    in-process L1 dict, so tests stay independent."""
    yield
    card_cache_module._l1.clear()
    r = redis.from_url(settings.REDIS_URL)
    for key in r.scan_iter(match="ubb:cardver:*"):
        r.delete(key)


def test_caller_billed_is_exact(tenant, customer):
    e = EstimationService.estimate(
        tenant, customer, event_type="x", provider="", usage_metrics=None,
        tags=None, currency="usd", caller_billed=777, caller_provider_cost=None,
        units=None)
    assert (e.micros, e.exact) == (777, True)


def test_linear_estimate_equals_exact_price(tenant, customer, price_card_fixture):
    CardCache.begin_request(tenant.id)
    e = EstimationService.estimate(
        tenant, customer, event_type="llm_call", provider="openai",
        usage_metrics={"tokens": 12_000}, tags={}, currency="usd",
        caller_billed=None, caller_provider_cost=None, units=None)
    _, exact_billed, _ = PricingService.price(
        tenant=tenant, customer=customer, event_type="llm_call", provider="openai",
        usage_metrics={"tokens": 12_000}, tags={}, currency="usd",
        caller_provider_cost=None, caller_billed=None)
    assert e.micros == exact_billed and e.exact is True


def test_markup_only_event_matches_pricer(tenant, customer):
    """usage_metrics empty + units > 0, no caller costs, non-strict tenant:
    the real pricer bills MarkupService.apply(0) — it does NOT fail. The
    estimate must match it exactly, not raise Unpriceable."""
    TenantMarkup.objects.create(tenant=tenant, customer=None,
                                markup_percentage_micros=10_000_000,
                                fixed_uplift_micros=25_000)
    CardCache.begin_request(tenant.id)
    e = EstimationService.estimate(
        tenant, customer, event_type="api_call", provider="",
        usage_metrics=None, tags={}, currency="usd",
        caller_billed=None, caller_provider_cost=None, units=5)
    _, exact_billed, _ = PricingService.price(
        tenant=tenant, customer=customer, event_type="api_call", provider="",
        usage_metrics=None, tags={}, currency="usd",
        caller_provider_cost=None, caller_billed=None, units=5)
    assert e.micros == exact_billed and e.exact is True


def test_nonstrict_unknown_metric_falls_back_to_markup(tenant, customer):
    """Non-strict tenant, metric with no price/cost card anywhere: the real
    pricer treats the cost as 0 and bills markup(0) — estimation must mirror
    that, not raise a spurious Unpriceable."""
    CardCache.begin_request(tenant.id)
    e = EstimationService.estimate(
        tenant, customer, event_type="unknown", provider="",
        usage_metrics={"mystery": 5}, tags={}, currency="usd",
        caller_billed=None, caller_provider_cost=None, units=None)
    _, exact_billed, _ = PricingService.price(
        tenant=tenant, customer=customer, event_type="unknown", provider="",
        usage_metrics={"mystery": 5}, tags={}, currency="usd",
        caller_provider_cost=None, caller_billed=None)
    assert e.micros == exact_billed and e.exact is True


def test_unpriceable_raises(tenant, customer):
    """Strict-coverage tenant with an uncosted metric: the real pricer raises
    PricingError, so estimation must route the item down the sync path."""
    tenant.require_cost_card_coverage = True
    tenant.save(update_fields=["require_cost_card_coverage"])
    CardCache.begin_request(tenant.id)
    with pytest.raises(Unpriceable):
        EstimationService.estimate(
            tenant, customer, event_type="unknown", provider="",
            usage_metrics={"mystery": 5}, tags={}, currency="usd",
            caller_billed=None, caller_provider_cost=None, units=None)


def test_strict_priced_metric_without_cost_card_raises(
        tenant, customer, price_card_fixture):
    """Strict-coverage tenant, metric HAS a price card but NO cost card: the
    real pricer raises PricingError in its cost section before pricing, so
    estimation must raise Unpriceable even though a price card matched."""
    tenant.require_cost_card_coverage = True
    tenant.save(update_fields=["require_cost_card_coverage"])
    CardCache.begin_request(tenant.id)
    with pytest.raises(Unpriceable):
        EstimationService.estimate(
            tenant, customer, event_type="llm_call", provider="openai",
            usage_metrics={"tokens": 12_000}, tags={}, currency="usd",
            caller_billed=None, caller_provider_cost=None, units=None)
