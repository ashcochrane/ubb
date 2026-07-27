import pytest
from django.db import IntegrityError
from apps.platform.tenants.models import Tenant
from apps.metering.pricing.models import Rate
from apps.metering.pricing.tests._helpers import rate_in_default_book


@pytest.mark.django_db
class TestRateSelectors:
    def _t(self):
        return Tenant.objects.create(name="T")

    def test_jsonb_dimensions_are_gone(self):
        names = {f.name for f in Rate._meta.get_fields()}
        assert "dimensions" not in names
        assert "dimensions_hash" not in names

    def test_specificity_counts_non_empty_selectors(self):
        t = self._t()
        r = rate_in_default_book(t, card_type="cost", provider="openai",
                                 event_type="chat", metric_name="input_tokens",
                                 dim1="eu-west-1")
        assert r.specificity == 3

    def test_wildcard_rate_has_zero_specificity(self):
        t = self._t()
        r = rate_in_default_book(t, card_type="cost", metric_name="input_tokens")
        assert r.specificity == 0

    def test_uniqueness_spans_all_selectors(self):
        t = self._t()
        rate_in_default_book(t, card_type="cost", provider="openai",
                             metric_name="input_tokens", dim1="eu")
        # Same book, same metric, DIFFERENT dim1 -> allowed.
        rate_in_default_book(t, card_type="cost", provider="openai",
                             metric_name="input_tokens", dim1="us")
        assert Rate.objects.filter(metric_name="input_tokens").count() == 2

    def test_duplicate_selector_set_is_rejected(self):
        t = self._t()
        rate_in_default_book(t, card_type="cost", provider="openai",
                             metric_name="input_tokens", dim1="eu")
        with pytest.raises(IntegrityError):
            rate_in_default_book(t, card_type="cost", provider="openai",
                                 metric_name="input_tokens", dim1="eu")
