"""`0012`'s backfill, replayed against the table it actually ran against.

⚠ **IT USED TO RUN AGAINST THE LIVE MODELS, AND THAT ONLY EVER WORKED BY
COINCIDENCE (#367).** The backfill groups pre-book rules into books, reading a
kind word off each rule to decide which book it belongs in. That column is
deleted and the table is renamed, so driving a data function from June through
today's registry asks for a field that does not exist on a relation that does
not exist. The fixture below reconstructs both — the name, and the shape — for
the duration of each test, which is what replaying a migration has always meant
and what this module was getting for free.

Every row here is therefore built through the HISTORICAL model rather than the
live one. That is not a workaround: a rule with no book cannot be expressed on
the live model at all, and it is the input this backfill exists to convert.

**NOTHING HERE NAMES A COLUMN IT DOES NOT NEED**, which is worth saying because
the state this replays is three renames old and carries several retired words.
The grouping is decided by tenant, kind, provider, currency and customer, so
those are what the rows state; the quantity a rule prices is not part of the
grouping and is left unset, where the reconstruction above makes it writable.
"""
import pytest
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from apps.metering.pricing.tests._helpers import (
    THE_RULES_KIND_COLUMN, reconcile_the_rate_table_with, restore_the_shape_of,
    the_pricing_tables_as_this_migration_saw_them, the_state_before)
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer

pytestmark = pytest.mark.django_db

APP_LABEL = "pricing"
BACKFILL = "0012_backfill_books"

#: The kind word `0012` reads off each rule to decide which book it belongs in.
#: This module's subject is a migration that ran while the column existed, so it
#: has to name it; `_helpers` carries the one assembled spelling and the reason
#: it is assembled.
THE_KIND = THE_RULES_KIND_COLUMN


@pytest.fixture
def historical():
    """The models `0012` saw, over a table reconstructed to match them."""
    migration = MigrationLoader(connection).get_migration(APP_LABEL, BACKFILL)
    state = the_state_before(migration)
    with the_pricing_tables_as_this_migration_saw_them(migration):
        apps = state.apps
        reconcile_the_rate_table_with(apps.get_model(APP_LABEL, "Rate"))
        # THE OTHER TWO TABLES 0012 WROTE, RECONSTRUCTED THE SAME WAY (#368).
        # The container lost three columns to the split and the record that
        # assigned a book to a customer was deleted outright, so one needs its
        # columns back and the other needs to exist at all.
        for name in ("RateCard", "RateCardAssignment"):
            restore_the_shape_of(apps.get_model(APP_LABEL, name))
        yield apps


@pytest.fixture
def rules(historical):
    return historical.get_model(APP_LABEL, "Rate")


@pytest.fixture
def assignments(historical):
    return historical.get_model(APP_LABEL, "RateCardAssignment")


@pytest.fixture
def books(historical):
    return historical.get_model(APP_LABEL, "RateCard")


@pytest.fixture
def backfill(historical):
    """The migration's own data function, over the state it ran in."""
    from apps.metering.pricing.migrations import _book_backfill

    def run():
        _book_backfill.forwards(historical, None)
    return run


def _rule(rules, tenant, *, kind="price", provider="gemini", currency="usd",
          customer=None, rate_per_unit_micros=10):
    return rules.objects.create(
        tenant_id=tenant.id, provider=provider, currency=currency,
        customer_id=customer.id if customer else None,
        rate_per_unit_micros=rate_per_unit_micros, **{THE_KIND: kind})


def test_default_rates_grouped_into_per_provider_default_book(rules, books,
                                                              backfill):
    t = Tenant.objects.create(name="T", default_currency="usd")
    r1 = _rule(rules, t, rate_per_unit_micros=10)
    r2 = _rule(rules, t, rate_per_unit_micros=30)
    backfill()
    r1.refresh_from_db(); r2.refresh_from_db()
    assert r1.rate_card_id is not None
    assert r1.rate_card_id == r2.rate_card_id  # same provider -> same book
    book = books.objects.get(id=r1.rate_card_id)
    assert book.is_default is True
    assert book.provider_key == "gemini"
    assert r1.book_version_from == 1 and r1.book_version_to is None


def test_customer_scoped_price_rate_gets_book_and_assignment(rules, books,
                                                             assignments,
                                                             backfill):
    t = Tenant.objects.create(name="T", default_currency="usd")
    c = Customer.objects.create(tenant=t, external_id="c1")
    r = _rule(rules, t, customer=c, rate_per_unit_micros=5)
    backfill()
    r.refresh_from_db()
    assert books.objects.get(id=r.rate_card_id).is_default is False
    a = assignments.objects.get(tenant_id=t.id, customer_id=c.id,
                                currency="usd")
    assert a.rate_card_id == r.rate_card_id


def test_same_provider_two_currencies_get_separate_books(rules, books,
                                                         backfill):
    t = Tenant.objects.create(name="T", default_currency="usd")
    usd = _rule(rules, t, currency="usd", rate_per_unit_micros=10)
    eur = _rule(rules, t, currency="eur", rate_per_unit_micros=9)
    backfill()
    usd.refresh_from_db(); eur.refresh_from_db()
    assert usd.rate_card_id != eur.rate_card_id
    assert books.objects.get(id=usd.rate_card_id).currency == "usd"
    assert books.objects.get(id=eur.rate_card_id).currency == "eur"


def test_backfill_raises_on_orphaned_customer_cost_rate(rules, backfill):
    t = Tenant.objects.create(name="T", default_currency="usd")
    c = Customer.objects.create(tenant=t, external_id="c1")
    _rule(rules, t, kind="cost", customer=c, rate_per_unit_micros=3)
    with pytest.raises(RuntimeError, match="customer-scoped cost"):
        backfill()


def test_multi_provider_customer_shares_one_book_and_assignment(rules,
                                                                assignments,
                                                                backfill):
    t = Tenant.objects.create(name="T", default_currency="usd")
    c = Customer.objects.create(tenant=t, external_id="c1")
    g = _rule(rules, t, provider="gemini", customer=c, rate_per_unit_micros=5)
    o = _rule(rules, t, provider="openai", customer=c, rate_per_unit_micros=6)
    backfill()
    g.refresh_from_db(); o.refresh_from_db()
    assert g.rate_card_id == o.rate_card_id
    assert assignments.objects.filter(tenant_id=t.id, customer_id=c.id,
                                      currency="usd").count() == 1
    a = assignments.objects.get(tenant_id=t.id, customer_id=c.id,
                                currency="usd")
    assert a.rate_card_id == g.rate_card_id
