"""Task 5: pins the two-level spend-pool resolution so it stops being folklore.

There are two month-to-date spend counters, deliberately not merged (see the
billing glossary's "Live counter" entry and its entry for the pool — still under
the pool's retired name until the fold, #470, rewrites it):

  ``ubb:spend_pool:{seat}:{YYYY-MM}``     -- SEAT-keyed. Drives the start-gate and
                                         the threshold alerts. Resolved via
                                         ``CustomerSpendPoolService.resolve_config_for``
                                         (seat's own row first, tenant default
                                         second).
  ``ubb:livespend:{owner}:{YYYY-MM}`` -- OWNER-keyed. Drives the postpaid live
                                         crossing. Resolved via
                                         ``LiveCounter._threshold`` against
                                         the OWNER's own row (falling back to
                                         the tenant default, never the seat's).

For a standalone customer these coincide (owner == seat). For a pooled
business they diverge on purpose: per-seat start caps plus one
owner-aggregate stop line. These tests pin both resolution rules and prove
the two counters never leak into each other.

Counter/flag state is fabricated ONLY through ``Door`` (the live_counter
module's own instruction: tests must never import its key helpers or the raw
client directly).
"""
import pytest
from django.core.cache import cache

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

    def test_live_counter_threshold_resolves_the_owners_own_row(self):
        """LiveCounter._threshold("postpaid", owner, tenant) -- the postpaid
        live crossing -- resolves the OWNER's (business's) own CustomerSpendPool
        row, not the seat's, even when both exist with different caps."""
        t, biz, seat = self._pooled_business()
        CustomerSpendPool.objects.create(tenant=t, customer=seat, cap_micros=200_000,
                                    hard_stop_pct=100, enforce_mode="blocking")
        owner_cfg = CustomerSpendPool.objects.create(tenant=t, customer=biz, cap_micros=900_000,
                                                hard_stop_pct=100, enforce_mode="blocking")

        threshold = LiveCounter._threshold("postpaid", biz.id, t)

        assert threshold == spend_pool_stop_threshold(owner_cfg)
        seat_threshold = spend_pool_stop_threshold(CustomerSpendPoolService.resolve_config_for(t.id, seat.id))
        assert threshold != seat_threshold

    def test_live_counter_threshold_falls_back_to_tenant_default_when_business_has_none(self):
        """A business with no CustomerSpendPool row of its own falls back to the
        TENANT default -- never to a seat's row, even though a seat under it
        has one configured."""
        t, biz, seat = self._pooled_business()
        CustomerSpendPool.objects.create(tenant=t, customer=seat, cap_micros=200_000,
                                    hard_stop_pct=100, enforce_mode="blocking")
        default_cfg = CustomerSpendPool.objects.create(tenant=t, customer=None, cap_micros=5_000_000,
                                                  hard_stop_pct=100, enforce_mode="blocking")
        # No CustomerSpendPool row for `biz` itself.

        threshold = LiveCounter._threshold("postpaid", biz.id, t)

        assert threshold == spend_pool_stop_threshold(default_cfg)

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
