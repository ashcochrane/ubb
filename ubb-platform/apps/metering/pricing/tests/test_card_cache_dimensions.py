import pytest
from django.utils import timezone
from django.test.utils import CaptureQueriesContext
from django.db import connection
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import Rate
from apps.metering.pricing.services import card_cache as card_cache_module
from apps.metering.pricing.services.card_cache import CardCache
from apps.metering.pricing.tests._helpers import rate_in_default_book


def _sel(**kw):
    """A fully-wildcarded selector map, overridden by whatever the caller pins.

    Built from `Rate.SELECTORS` rather than transcribed: the resolver reads that
    tuple, so a map written by hand is one that can silently stop covering a
    selector the resolver still consults.
    """
    return {**{selector: "" for selector in Rate.SELECTORS}, **kw}


@pytest.mark.django_db
class TestCardCacheDimensions:
    def _tc(self):
        """Reset via the module-private _l1 and begin_request, matching the
        convention the existing test_card_cache.py uses (lines 52, 62)."""
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        rate_in_default_book(t, card_type="cost", provider="openai", grouping_field_1="eu",
                             measurement_key="input_tokens", rate_per_unit_micros=1_000,
                             unit_quantity=1_000_000)
        card_cache_module._l1.clear()
        CardCache.begin_request(t.id)
        # The instant is part of the key now, so every resolve in one test has
        # to ask about the SAME moment or the "second resolve" is a first one.
        return t, c, timezone.now()

    def test_slot_bearing_resolution_is_cached(self):
        """Before this change CardCache bypassed L1 whenever the open bag was
        non-empty (card_cache.py:67-73), so every event carrying a slot value
        hit Postgres.
        Bounded cardinality (design D4) is what makes the key safe."""
        t, c, now = self._tc()
        sel = _sel(provider="openai", grouping_field_1="eu")
        CardCache.resolve(t, c, "cost", sel, "input_tokens", "usd", now)
        with CaptureQueriesContext(connection) as ctx:
            CardCache.resolve(t, c, "cost", sel, "input_tokens", "usd", now)
        assert len(ctx) == 0, "second resolve must be served from L1"

    def test_different_dimension_values_do_not_collide(self):
        t, c, now = self._tc()
        hit = CardCache.resolve(t, c, "cost", _sel(provider="openai", grouping_field_1="eu"),
                                "input_tokens", "usd", now)
        miss = CardCache.resolve(t, c, "cost", _sel(provider="openai", grouping_field_1="us"),
                                 "input_tokens", "usd", now)
        assert hit is not None and miss is None

    def test_invalidation_forces_a_re_resolve(self):
        """invalidate() bumps the Redis version counter; a NEW request observes
        the bump via begin_request, which is what stales the L1 entry."""
        t, c, now = self._tc()
        sel = _sel(provider="openai", grouping_field_1="eu")
        CardCache.resolve(t, c, "cost", sel, "input_tokens", "usd", now)
        CardCache.invalidate(t.id)
        CardCache.begin_request(t.id)
        with CaptureQueriesContext(connection) as ctx:
            CardCache.resolve(t, c, "cost", sel, "input_tokens", "usd", now)
        assert len(ctx) > 0, "a version bump must force a re-resolve"
