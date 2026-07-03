import pytest
from django.core.management import call_command
from django.utils import timezone
from apps.metering.pricing.models import Rate, RateCard, RateCardAssignment
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer

pytestmark = pytest.mark.django_db


def _backfill():
    # The migration's data function, callable directly for the test.
    from apps.metering.pricing.migrations import _book_backfill
    from django.apps import apps as django_apps
    _book_backfill.forwards(django_apps, None)


def test_default_rates_grouped_into_per_provider_default_book():
    t = Tenant.objects.create(name="T", default_currency="usd")
    r1 = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                             metric_name="input_tokens", currency="usd",
                             rate_per_unit_micros=10)
    r2 = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                             metric_name="output_tokens", currency="usd",
                             rate_per_unit_micros=30)
    _backfill()
    r1.refresh_from_db(); r2.refresh_from_db()
    assert r1.rate_card_id is not None
    assert r1.rate_card_id == r2.rate_card_id  # same provider -> same book
    assert r1.rate_card.is_default is True
    assert r1.rate_card.provider_key == "gemini"
    assert r1.book_version_from == 1 and r1.book_version_to is None


def test_customer_scoped_price_rate_gets_book_and_assignment():
    t = Tenant.objects.create(name="T", default_currency="usd")
    c = Customer.objects.create(tenant=t, external_id="c1")
    r = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                            metric_name="input_tokens", currency="usd",
                            customer=c, rate_per_unit_micros=5)
    _backfill()
    r.refresh_from_db()
    assert r.rate_card.is_default is False
    a = RateCardAssignment.objects.get(tenant=t, customer=c, currency="usd")
    assert a.rate_card_id == r.rate_card_id
