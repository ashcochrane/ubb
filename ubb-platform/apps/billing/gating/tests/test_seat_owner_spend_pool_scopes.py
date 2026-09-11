"""Task 5: pins the two-level spend-pool resolution so it stops being folklore.

There are two month-to-date spend counters, deliberately not merged (see the
billing glossary's "Live counter" entry and its entry for the pool — still under
the pool's retired name until the fold, #470, rewrites it), and since #459
they are the pool's TWO DECLARED LEVELS (slice 6 §4):

  ``ubb:spend_pool:{seat}:{YYYY-MM}``     -- SEAT-keyed. Drives the start-gate,
                                         the threshold alerts and the seat
                                         level's durable-lane stop. Resolved
                                         via ``CustomerSpendPoolService.
                                         resolve_config_for`` (seat's own row
                                         first, tenant default second).
  ``ubb:livespend:{owner}:{YYYY-MM}`` -- OWNER-keyed. Drives the owner level's
                                         live crossing in EVERY mode. Resolved
                                         via ``LiveCounter._owner_pool`` against
                                         the OWNER's own row — never the seat's,
                                         and never the tenant default for a
                                         business: THE DEFAULT REACHES SEATS
                                         ONLY, so one configured number never
                                         becomes two lines at two altitudes.

For a standalone customer these coincide (owner == seat). For a pooled
business they diverge on purpose: per-seat lines plus one owner-aggregate
line. These tests pin both resolution rules and prove the two counters never
leak into each other.

Counter/flag state is fabricated ONLY through ``Door`` (the live_counter
module's own instruction: tests must never import its key helpers or the raw
client directly).
"""
import pytest
from django.core.cache import cache
from django.utils import timezone

from core.crossing import spend_pool_stop_threshold
from apps.billing.gating.models import CustomerSpendPool
from apps.billing.gating.services.customer_spend_pool_service import CustomerSpendPoolService
from apps.billing.gating.services.live_counter import Door, LiveCounter
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestSeatOwnerSpendPoolScopes:
    def setup_method(self):
        cache.clear()

    def _pooled_business(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="postpaid", enforcement_mode="enforcing")
        biz = Customer.objects.create(tenant=t, external_id="biz",
                                      account_type="business", billing_topology="pooled")
        seat = Customer.objects.create(tenant=t, external_id="seat1",
                                       account_type="seat", parent=biz)
        assert seat.resolve_billing_owner().id == biz.id  # sanity: pooled -> business
        return t, biz, seat

    def test_resolve_config_for_prefers_the_seats_own_row(self):
        """CustomerSpendPoolService.resolve_config_for(tenant, seat) -- the start-gate
        and threshold-alert resolution -- returns the SEAT's own row even
        though the owner (business) and the tenant default both have rows
        of their own. A seat's cap is never satisfied by its business's cap,
        or vice versa."""
        t, biz, seat = self._pooled_business()
        CustomerSpendPool.objects.create(tenant=t, customer=None, cap_micros=1_000_000)  # tenant default
        seat_cfg = CustomerSpendPool.objects.create(tenant=t, customer=seat, cap_micros=200_000)
        CustomerSpendPool.objects.create(tenant=t, customer=biz, cap_micros=900_000)  # owner's OWN row

        resolved = CustomerSpendPoolService.resolve_config_for(t.id, seat.id)

        assert resolved.id == seat_cfg.id
        assert resolved.cap_micros == 200_000

    def test_the_owner_level_resolves_the_owners_own_row(self):
        """LiveCounter._owner_pool(owner, tenant) -- the owner level's live
        crossing -- resolves the OWNER's (business's) own CustomerSpendPool
        row, not the seat's, even when both exist with different caps."""
        t, biz, seat = self._pooled_business()
        CustomerSpendPool.objects.create(tenant=t, customer=seat, cap_micros=200_000,
                                    hard_stop_pct=100, enforce_mode="blocking")
        owner_cfg = CustomerSpendPool.objects.create(tenant=t, customer=biz, cap_micros=900_000,
                                                hard_stop_pct=100, enforce_mode="blocking")

        pool = LiveCounter._owner_pool(biz.id, t)

        assert pool.id == owner_cfg.id
        seat_threshold = spend_pool_stop_threshold(CustomerSpendPoolService.resolve_config_for(t.id, seat.id))
        assert spend_pool_stop_threshold(pool) != seat_threshold

    def test_a_business_with_no_row_of_its_own_has_no_pool(self):
        """The tenant default applies to SEATS ONLY (slice 6 §4, #459): a
        business with no CustomerSpendPool row of its own has no pool at all
        -- never the tenant default, never a seat's row -- while the seat
        under it still resolves the default. One configured number is never
        two lines at two altitudes."""
        t, biz, seat = self._pooled_business()
        default_cfg = CustomerSpendPool.objects.create(tenant=t, customer=None, cap_micros=5_000_000,
                                                  hard_stop_pct=100, enforce_mode="blocking")
        # No CustomerSpendPool row for `biz` itself.

        assert LiveCounter._owner_pool(biz.id, t) is None
        assert CustomerSpendPoolService.resolve_config_for(t.id, biz.id) is None
        assert CustomerSpendPoolService.resolve_config(biz) is None
        assert CustomerSpendPoolService.resolve_config_for(t.id, seat.id).id == default_cfg.id
        # A business's own usage never crosses a line nobody declared for it.
        Door.set_spend(biz.id, 10_000_000)
        assert LiveCounter.debit(biz.id, t, 1, now=timezone.now())["stop"] is False

    def test_seat_budget_counter_and_owner_livespend_counter_are_independent(self):
        """The two Redis counters are different keys with independent state
        -- moving one must never move the other, regardless of the seat
        belonging to the owner being read."""
        t, biz, seat = self._pooled_business()

        Door.set_spend_pool(seat.id, 300_000)
        Door.set_spend(biz.id, 700_000)

        assert CustomerSpendPoolService.current_spend(t.id, seat.id) == 300_000
        assert Door.spend(biz.id) == 700_000

        Door.set_spend_pool(seat.id, 999_000)
        assert Door.spend(biz.id) == 700_000  # untouched by the seat counter's move

        Door.set_spend(biz.id, 111_000)
        assert CustomerSpendPoolService.current_spend(t.id, seat.id) == 999_000  # untouched by the owner's move
