import pytest
from django.db import IntegrityError
from apps.metering.pricing.models import RateCard, RateCardAssignment
from apps.platform.tenants.models import Tenant

pytestmark = pytest.mark.django_db


def _tenant():
    return Tenant.objects.create(name="T", default_currency="usd")


def test_one_default_book_per_tenant_cardtype_provider_currency():
    t = _tenant()
    RateCard.objects.create(tenant=t, card_type="price", currency="usd",
                            key="gemini", name="Gemini", provider_key="gemini",
                            is_default=True)
    # A second default book for the SAME (tenant, card_type, provider, currency)
    # must be rejected. `provider_key` is the field the DB constraint keys on
    # (both inserts share it so this isolates the is_default partial-unique
    # constraint from the unrelated tenant+card_type+key uniqueness).
    with pytest.raises(IntegrityError):
        RateCard.objects.create(tenant=t, card_type="price", currency="usd",
                                key="gemini-2", name="Gemini 2", provider_key="gemini",
                                is_default=True)


def test_assignment_unique_per_customer_currency():
    from apps.platform.customers.models import Customer
    t = _tenant()
    c = Customer.objects.create(tenant=t, external_id="c1")
    book = RateCard.objects.create(tenant=t, card_type="price", currency="usd",
                                   key="ent", name="Enterprise")
    RateCardAssignment.objects.create(tenant=t, customer=c, rate_card=book, currency="usd")
    with pytest.raises(IntegrityError):
        RateCardAssignment.objects.create(tenant=t, customer=c, rate_card=book, currency="usd")
