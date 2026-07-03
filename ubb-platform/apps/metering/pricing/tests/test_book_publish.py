import pytest
from django.utils import timezone
from apps.metering.pricing.models import Rate, RateCard
from apps.metering.pricing.services.book_service import BookService
from apps.platform.tenants.models import Tenant

pytestmark = pytest.mark.django_db


def _book_with_two_rates():
    t = Tenant.objects.create(name="T", default_currency="usd")
    book = RateCard.objects.create(tenant=t, card_type="price", provider_key="gemini",
                                   currency="usd", key="gemini", is_default=True, version=1)
    ri = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                             metric_name="input_tokens", currency="usd",
                             rate_per_unit_micros=10, rate_card=book, book_version_from=1)
    ro = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                             metric_name="output_tokens", currency="usd",
                             rate_per_unit_micros=30, rate_card=book, book_version_from=1)
    return t, book, ri, ro


def test_publish_supersedes_and_bumps_version_atomically():
    t, book, ri, ro = _book_with_two_rates()
    BookService.publish(book, changes=[
        {"metric_name": "input_tokens", "provider": "gemini", "event_type": "",
         "dimensions": {}, "rate_per_unit_micros": 12},
        {"metric_name": "output_tokens", "provider": "gemini", "event_type": "",
         "dimensions": {}, "rate_per_unit_micros": 33},
    ])
    book.refresh_from_db(); ri.refresh_from_db(); ro.refresh_from_db()
    assert book.version == 2
    # Old rows closed at v1, new active rows opened at v2.
    assert ri.valid_to is not None and ri.book_version_to == 1
    assert ro.valid_to is not None and ro.book_version_to == 1
    active = list(Rate.objects.filter(rate_card=book, valid_to__isnull=True).order_by("metric_name"))
    assert [a.rate_per_unit_micros for a in active] == [12, 33]
    assert all(a.book_version_from == 2 for a in active)
    # lineage preserved (tiered continuity guarantee).
    assert {a.lineage_id for a in active} == {ri.lineage_id, ro.lineage_id}


def test_publish_is_all_or_nothing_on_error():
    t, book, ri, ro = _book_with_two_rates()
    with pytest.raises(Exception):
        BookService.publish(book, changes=[
            {"metric_name": "input_tokens", "provider": "gemini", "event_type": "",
             "dimensions": {}, "rate_per_unit_micros": 12},
            {"metric_name": "MISSING", "provider": "gemini", "event_type": "",
             "dimensions": {}, "rate_per_unit_micros": 1},  # no active rate -> error
        ])
    book.refresh_from_db()
    assert book.version == 1  # rolled back
    assert Rate.objects.filter(rate_card=book, valid_to__isnull=True).count() == 2
    ri.refresh_from_db(); ro.refresh_from_db()
    assert ri.valid_to is None and ro.valid_to is None  # originals still active, not superseded
    active_ids = set(Rate.objects.filter(rate_card=book, valid_to__isnull=True)
                     .values_list("id", flat=True))
    assert active_ids == {ri.id, ro.id}  # exactly the originals; no new row leaked in


def test_publish_preserves_lineage_for_tiered_marginal_continuity():
    t = Tenant.objects.create(name="T", default_currency="usd")
    book = RateCard.objects.create(tenant=t, card_type="price", provider_key="gemini",
                                   currency="usd", key="gemini", is_default=True, version=1)
    r = Rate.objects.create(tenant=t, card_type="price", provider="gemini",
                            metric_name="input_tokens", currency="usd",
                            pricing_model="graduated",
                            tiers=[{"up_to": 1000, "rate_per_unit_micros": 10},
                                   {"up_to": None, "rate_per_unit_micros": 5}],
                            rate_card=book, book_version_from=1)
    old_lineage = r.lineage_id
    BookService.publish(book, changes=[{
        "metric_name": "input_tokens", "provider": "gemini", "event_type": "",
        "dimensions": {}, "pricing_model": "graduated",
        "tiers": [{"up_to": 1000, "rate_per_unit_micros": 12},
                  {"up_to": None, "rate_per_unit_micros": 6}]}])
    new = Rate.objects.get(rate_card=book, valid_to__isnull=True)
    assert new.lineage_id == old_lineage  # PricingPeriodCounter continuity intact
