import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.pricing.services import card_cache as card_cache_module
from apps.metering.pricing.services.card_cache import CardCache
from apps.metering.pricing.tests._helpers import rate_in_default_book


def _sel(**kw):
    base = {"provider": "", "event_type": "", "task_type": "", "subtask_type": "",
            "grouping_field_1": "", "grouping_field_2": "", "grouping_field_3": "", "grouping_field_4": "", "grouping_field_5": "", "grouping_field_6": "", "grouping_field_7": "", "grouping_field_8": "", "grouping_field_9": "", "grouping_field_10": ""}
    base.update(kw)
    return base


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
        return t, c

    def test_dimension_bearing_resolution_is_cached(self):
        """Before this change CardCache bypassed L1 whenever the open bag was
        non-empty (card_cache.py:67-73), so every dimension-bearing event hit
        Postgres.
        Bounded cardinality (design D4) is what makes the key safe."""
        t, c = self._tc()
        sel = _sel(provider="openai", grouping_field_1="eu")
        CardCache.resolve(t, c, "cost", sel, "input_tokens", "usd")
        with CaptureQueriesContext(connection) as ctx:
            CardCache.resolve(t, c, "cost", sel, "input_tokens", "usd")
        assert len(ctx) == 0, "second resolve must be served from L1"

    def test_different_dimension_values_do_not_collide(self):
        t, c = self._tc()
        hit = CardCache.resolve(t, c, "cost", _sel(provider="openai", grouping_field_1="eu"),
                                "input_tokens", "usd")
        miss = CardCache.resolve(t, c, "cost", _sel(provider="openai", grouping_field_1="us"),
                                 "input_tokens", "usd")
        assert hit is not None and miss is None

    def test_invalidation_forces_a_re_resolve(self):
        """invalidate() bumps the Redis version counter; a NEW request observes
        the bump via begin_request, which is what stales the L1 entry."""
        t, c = self._tc()
        sel = _sel(provider="openai", grouping_field_1="eu")
        CardCache.resolve(t, c, "cost", sel, "input_tokens", "usd")
        CardCache.invalidate(t.id)
        CardCache.begin_request(t.id)
        with CaptureQueriesContext(connection) as ctx:
            CardCache.resolve(t, c, "cost", sel, "input_tokens", "usd")
        assert len(ctx) > 0, "a version bump must force a re-resolve"
