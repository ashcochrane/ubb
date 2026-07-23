"""#111 — the live counter's OWN pin test: key formats frozen ONCE, here.

Every physical Redis key format the live counter owns is asserted in exactly
one place — this file — instead of being frozen implicitly by ~30 scattered
private-import sites (the pre-#111 disease). The perimeter walker
(``apps/billing/tests/test_live_counter_perimeter.py``) guarantees no other
module (production OR the module's other tests) spells these literals, so a
key-format change is a ONE-file conversation: the module + this pin.

The assertions drive the PUBLIC ops (and the test door) and observe the
physical keyspace with an independent raw client — proving the formats from
the outside, not by importing the private helpers they pin.
"""
import pytest
import redis
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.billing.gating.crossing import month_label_bounds
from apps.billing.gating.services.live_counter import (Door, LiveCounter,
                                                       stop_channel)
from apps.billing.wallets.models import Wallet
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _flush():
    cache.clear()  # FLUSHDB of the dedicated test Redis db (root conftest)
    yield


def _raw():
    # An independent raw connection to the same test db — deliberately NOT
    # the module's _client(), so these pins observe the physical keyspace
    # from outside the module.
    return redis.from_url(settings.REDIS_URL)


def _label():
    return month_label_bounds(timezone.now())[0]


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode="prepaid",
                                 enforcement_mode="enforcing")


@pytest.fixture
def owner(tenant):
    c = Customer.objects.create(tenant=tenant, external_id="pin-owner")
    Wallet.objects.create(customer=c, balance_micros=20_000_000)
    return c


def test_prepaid_balance_key_format(tenant, owner):
    LiveCounter.debit(owner.id, tenant, 3_000_000)
    assert _raw().get(f"ubb:livebal:{owner.id}") == b"17000000"
    assert Door.balance(owner.id) == 17_000_000  # the door reads the same key


def test_postpaid_livespend_key_format():
    t = Tenant.objects.create(name="TP", products=["metering", "billing"],
                              billing_mode="postpaid",
                              enforcement_mode="enforcing")
    c = Customer.objects.create(tenant=t, external_id="pin-pp")
    LiveCounter.debit(c.id, t, 4_000_000, now=timezone.now())
    assert _raw().get(f"ubb:livespend:{c.id}:{_label()}") == b"4000000"
    assert Door.spend(c.id) == 4_000_000


def test_stop_flag_key_format(tenant, owner):
    LiveCounter.debit(owner.id, tenant, 21_000_000)  # crosses the (0) floor
    assert _raw().get(f"ubb:stop:{owner.id}") == b"customer_wide_stop"
    assert Door.stop_reason(owner.id) == "customer_wide_stop"


def test_stop_channel_format(owner):
    # The one PUBLIC key-shaped name — subscribers live outside the module.
    assert stop_channel(owner.id) == f"ubb:stopchan:{owner.id}"


def test_budget_key_format(tenant):
    c = Customer.objects.create(tenant=tenant, external_id="pin-seat")
    Door.set_budget(c.id, 111)
    LiveCounter.budget_incr(tenant.id, c.id, 9)
    assert _raw().get(f"ubb:budget:{c.id}:{_label()}") == b"120"
    assert Door.budget(c.id) == 120


def test_counter_keys_carry_the_module_ttl(tenant, owner):
    # TTL discipline: every write refreshes the ~62-day expiry (a plain
    # positive TTL is asserted, not the exact constant — the pin is that keys
    # EXPIRE, the constant may be tuned).
    LiveCounter.debit(owner.id, tenant, 1_000_000)
    ttl = _raw().ttl(f"ubb:livebal:{owner.id}")
    assert 0 < ttl <= 62 * 24 * 3600
